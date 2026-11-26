import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { useTranslation } from 'react-i18next';
import {
  createPublicLiveGrant,
  getLiveStreamStatus,
  getPreparedLiveStreamChannel,
  listPublicLiveGrants,
  prepareLiveStream,
  revokePublicLiveGrant,
  stopLiveStream,
  type LiveStreamPrepareResponse,
  type LiveStreamPresence,
  type PublicLiveGrantListItem,
} from '../../api/liveStreamApi';
import type { Aisle } from '../../api/types';
import { useAppSnackbar } from '../../components/ui';
import { isApiNotPreparedError } from './liveStreamPresence';

export interface LiveStreamDialogProps {
  open: boolean;
  inventoryId: string;
  aisles: Aisle[];
  initialAisleCode?: string;
  onClose: () => void;
  onChannelsChanged?: () => void;
}

function buildRtmpEmbeddedAuthUrl(publishUrl: string, username: string, password: string): string {
  const trimmed = publishUrl.trim();
  const user = encodeURIComponent(username);
  const pass = encodeURIComponent(password);
  const sep = trimmed.includes('?') ? '&' : '?';
  return `${trimmed}${sep}user=${user}&pass=${pass}`;
}

const presenceLabelKey: Record<LiveStreamPresence, string> = {
  no_stream: 'live_stream.presence_no_stream',
  connecting: 'live_stream.presence_connecting',
  live: 'live_stream.presence_live',
  reconnecting: 'live_stream.presence_reconnecting',
  ended: 'live_stream.presence_ended',
  service_unavailable: 'live_stream.presence_service_unavailable',
};

export default function LiveStreamDialog({
  open,
  inventoryId,
  aisles,
  initialAisleCode,
  onClose,
  onChannelsChanged,
}: LiveStreamDialogProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [aisleCode, setAisleCode] = useState(initialAisleCode ?? '');
  const [prepared, setPrepared] = useState<LiveStreamPrepareResponse | null>(null);
  const [presence, setPresence] = useState<LiveStreamPresence>('no_stream');
  const [busy, setBusy] = useState(false);
  const [lastPublicUrl, setLastPublicUrl] = useState<string | null>(null);
  const [lastGrantId, setLastGrantId] = useState<string | null>(null);
  const [publishBlocked, setPublishBlocked] = useState(false);
  const [activeGrants, setActiveGrants] = useState<PublicLiveGrantListItem[]>([]);
  const [rtmpExpanded, setRtmpExpanded] = useState(false);

  const presenceLabel = useMemo(
    () => t(presenceLabelKey[presence] ?? presenceLabelKey.no_stream),
    [presence, t],
  );

  const syncFromPrepared = useCallback((result: LiveStreamPrepareResponse) => {
    setPrepared(result);
    setPresence(result.status.presence);
    setPublishBlocked(result.status.publish_blocked);
  }, []);

  const loadGrants = useCallback(
    async (code: string) => {
      try {
        const grants = await listPublicLiveGrants(inventoryId, code);
        const active = grants.filter((g) => g.revoked_at == null);
        setActiveGrants(active);
      } catch {
        setActiveGrants([]);
      }
    },
    [inventoryId],
  );

  const loadPreparedChannel = useCallback(
    async (code: string) => {
      const trimmed = code.trim();
      if (!trimmed) {
        setPrepared(null);
        setPresence('no_stream');
        setPublishBlocked(false);
        setActiveGrants([]);
        return;
      }
      try {
        const result = await getPreparedLiveStreamChannel(inventoryId, trimmed);
        syncFromPrepared(result);
        await loadGrants(trimmed);
      } catch (error) {
        if (isApiNotPreparedError(error)) {
          setPrepared(null);
          try {
            const status = await getLiveStreamStatus(inventoryId, trimmed);
            setPresence(status.presence);
            setPublishBlocked(status.publish_blocked);
          } catch {
            setPresence('service_unavailable');
          }
          setActiveGrants([]);
          return;
        }
        setPresence('service_unavailable');
      }
    },
    [inventoryId, loadGrants, syncFromPrepared],
  );

  useEffect(() => {
    if (!open) return;
    const nextCode = initialAisleCode ?? aisleCode;
    if (initialAisleCode) {
      setAisleCode(initialAisleCode);
    }
    setLastPublicUrl(null);
    setLastGrantId(null);
    setRtmpExpanded(false);
    void loadPreparedChannel(nextCode);
  }, [open, initialAisleCode]); // eslint-disable-line react-hooks/exhaustive-deps -- recover on open only

  useEffect(() => {
    if (!open) return undefined;
    const code = aisleCode.trim();
    if (!code) return undefined;
    void loadPreparedChannel(code);
  }, [aisleCode]); // eslint-disable-line react-hooks/exhaustive-deps -- aisle selection

  const refreshStatus = useCallback(async () => {
    if (!aisleCode.trim()) return;
    try {
      const status = await getLiveStreamStatus(inventoryId, aisleCode.trim());
      setPresence(status.presence);
      setPublishBlocked(status.publish_blocked);
      if (prepared) {
        setPrepared({ ...prepared, status });
      }
    } catch {
      setPresence('service_unavailable');
    }
  }, [aisleCode, inventoryId, prepared]);

  useEffect(() => {
    if (!open || !prepared) return undefined;
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 8000);
    return () => window.clearInterval(timer);
  }, [open, prepared, refreshStatus]);

  const handlePrepare = async () => {
    const code = aisleCode.trim();
    if (!code) return;
    setBusy(true);
    try {
      const result = await prepareLiveStream(inventoryId, code);
      syncFromPrepared(result);
      await loadGrants(code);
      showSnackbar(t('live_stream.prepare_success'), 'success');
      onChannelsChanged?.();
    } catch {
      showSnackbar(t('live_stream.prepare_error'), 'error');
      setPresence('service_unavailable');
    } finally {
      setBusy(false);
    }
  };

  const copyText = async (text: string, okKey: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showSnackbar(t(okKey), 'success');
    } catch {
      showSnackbar(t('live_stream.copy_failed'), 'error');
    }
  };

  const handlePublicLink = async () => {
    if (!aisleCode.trim()) return;
    setBusy(true);
    try {
      const grant = await createPublicLiveGrant(inventoryId, aisleCode.trim());
      setLastPublicUrl(grant.public_url);
      setLastGrantId(grant.grant_id);
      await loadGrants(aisleCode.trim());
      await copyText(grant.public_url, 'live_stream.public_link_copied');
    } catch {
      showSnackbar(t('live_stream.public_link_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenPublicViewer = () => {
    if (!lastPublicUrl) return;
    window.open(lastPublicUrl, '_blank', 'noopener,noreferrer');
  };

  const handleStopTransmission = async () => {
    const code = aisleCode.trim();
    if (!code) return;
    const ok = window.confirm(t('live_stream.stop_confirm'));
    if (!ok) return;
    setBusy(true);
    try {
      const result = await stopLiveStream(inventoryId, code);
      setPresence(result.status.presence);
      setPublishBlocked(result.status.publish_blocked);
      if (prepared) {
        setPrepared({ ...prepared, status: result.status });
      }
      showSnackbar(t('live_stream.stop_success'), 'success');
      onChannelsChanged?.();
    } catch {
      showSnackbar(t('live_stream.stop_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (grantId: string) => {
    setBusy(true);
    try {
      await revokePublicLiveGrant(inventoryId, grantId);
      if (lastGrantId === grantId) {
        setLastGrantId(null);
        setLastPublicUrl(null);
      }
      await loadGrants(aisleCode.trim());
      showSnackbar(t('live_stream.public_link_revoked'), 'success');
    } catch {
      showSnackbar(t('live_stream.public_link_revoke_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const channelPrepared = prepared !== null;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('live_stream.dialog_title')}</DialogTitle>
      <DialogContent sx={{ display: 'grid', gap: 2, pt: 1 }}>
        {aisles.length > 0 ? (
          <TextField
            select
            label={t('live_stream.aisle_code_label')}
            value={aisleCode}
            onChange={(e) => setAisleCode(e.target.value)}
            helperText={t('live_stream.aisle_code_help')}
            fullWidth
          >
            {aisles.map((a) => (
              <MenuItem key={a.id} value={a.code}>
                {a.code}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <TextField
            label={t('live_stream.aisle_code_label')}
            value={aisleCode}
            onChange={(e) => setAisleCode(e.target.value)}
            helperText={t('live_stream.aisle_code_help')}
            fullWidth
          />
        )}
        <Typography variant="body2" color="text.secondary">
          {t('live_stream.status_label')}: {presenceLabel}
          {publishBlocked ? ` — ${t('live_stream.publish_blocked_hint')}` : ''}
        </Typography>
        {channelPrepared && prepared ? (
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Accordion
              expanded={rtmpExpanded}
              onChange={(_, expanded) => setRtmpExpanded(expanded)}
              disableGutters
              elevation={0}
              sx={{ border: 1, borderColor: 'divider', '&:before': { display: 'none' } }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">{t('live_stream.rtmp_section')}</Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ display: 'grid', gap: 1 }}>
                <TextField
                  label={t('live_stream.rtmp_url')}
                  value={prepared.rtmp_publish_url}
                  InputProps={{ readOnly: true }}
                  fullWidth
                  size="small"
                />
                <TextField
                  label={t('live_stream.publish_username')}
                  value={prepared.publish_username}
                  InputProps={{ readOnly: true }}
                  fullWidth
                  size="small"
                />
                <TextField
                  label={t('live_stream.publish_password')}
                  value={prepared.publish_password}
                  InputProps={{ readOnly: true }}
                  fullWidth
                  size="small"
                />
                <Typography variant="caption" color="text.secondary">
                  {t('live_stream.dji_rtmp_help')}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  <Button
                    size="small"
                    onClick={() => void copyText(prepared.rtmp_publish_url, 'live_stream.rtmp_copied')}
                  >
                    {t('live_stream.copy_rtmp')}
                  </Button>
                  <Button
                    size="small"
                    onClick={() =>
                      void copyText(
                        buildRtmpEmbeddedAuthUrl(
                          prepared.rtmp_publish_url,
                          prepared.publish_username,
                          prepared.publish_password,
                        ),
                        'live_stream.rtmp_copied',
                      )
                    }
                  >
                    {t('live_stream.copy_rtmp_with_auth')}
                  </Button>
                </Box>
              </AccordionDetails>
            </Accordion>
            <Typography variant="subtitle2">{t('live_stream.public_section')}</Typography>
            {lastPublicUrl ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
                <Typography variant="body2" sx={{ wordBreak: 'break-all', flex: '1 1 100%' }}>
                  {lastPublicUrl}
                </Typography>
                <Button size="small" onClick={() => void copyText(lastPublicUrl, 'live_stream.public_link_copied')}>
                  {t('live_stream.copy_public_link')}
                </Button>
                <Button size="small" startIcon={<OpenInNewIcon />} onClick={handleOpenPublicViewer}>
                  {t('live_stream.open_public_viewer')}
                </Button>
              </Box>
            ) : activeGrants.length > 0 ? (
              <Alert severity="info" sx={{ py: 0 }}>
                {t('live_stream.public_link_not_stored')}
              </Alert>
            ) : null}
            {activeGrants.length > 0 ? (
              <Box sx={{ display: 'grid', gap: 0.5 }}>
                {activeGrants.map((g) => (
                  <Box key={g.grant_id} sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
                    <Typography variant="caption" color="text.secondary">
                      {t('live_stream.public_grant_expires', { date: new Date(g.expires_at).toLocaleString() })}
                    </Typography>
                    <Button size="small" color="warning" disabled={busy} onClick={() => void handleRevoke(g.grant_id)}>
                      {t('live_stream.revoke_public_link')}
                    </Button>
                  </Box>
                ))}
              </Box>
            ) : null}
          </Box>
        ) : null}
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Button onClick={onClose}>{t('common.close')}</Button>
        <Button onClick={() => void refreshStatus()} disabled={!aisleCode.trim() || busy}>
          {t('live_stream.refresh_status')}
        </Button>
        {!channelPrepared ? (
          <Button variant="contained" onClick={() => void handlePrepare()} disabled={!aisleCode.trim() || busy}>
            {t('live_stream.prepare_action')}
          </Button>
        ) : null}
        <Button
          onClick={() => void handleStopTransmission()}
          disabled={!channelPrepared || !aisleCode.trim() || busy}
          color="error"
        >
          {t('live_stream.stop_action')}
        </Button>
        <Button onClick={() => void handlePublicLink()} disabled={!channelPrepared || !aisleCode.trim() || busy}>
          {t('live_stream.public_link_action')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}