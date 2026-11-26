import { useCallback, useEffect, useMemo, useState } from 'react';
import {
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
import { useTranslation } from 'react-i18next';
import {
  createPublicLiveGrant,
  getLiveStreamStatus,
  prepareLiveStream,
  revokePublicLiveGrant,
  stopLiveStream,
  type LiveStreamPrepareResponse,
  type LiveStreamPresence,
} from '../../api/liveStreamApi';
import type { Aisle } from '../../api/types';
import { useAppSnackbar } from '../../components/ui';
import HlsLivePlayer from './HlsLivePlayer';

export interface LiveStreamDialogProps {
  open: boolean;
  inventoryId: string;
  aisles: Aisle[];
  initialAisleCode?: string;
  onClose: () => void;
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

  useEffect(() => {
    if (open) {
      setAisleCode(initialAisleCode ?? '');
      setPrepared(null);
      setPresence('no_stream');
      setLastPublicUrl(null);
      setLastGrantId(null);
      setPublishBlocked(false);
    }
  }, [open, initialAisleCode]);

  const presenceLabel = useMemo(
    () => t(presenceLabelKey[presence] ?? presenceLabelKey.no_stream),
    [presence, t],
  );

  const refreshStatus = useCallback(async () => {
    if (!aisleCode.trim()) return;
    try {
      const status = await getLiveStreamStatus(inventoryId, aisleCode.trim());
      setPresence(status.presence);
      setPublishBlocked(status.publish_blocked);
    } catch {
      setPresence('service_unavailable');
    }
  }, [aisleCode, inventoryId]);

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
      setPrepared(result);
      setPresence(result.status.presence);
      setPublishBlocked(result.status.publish_blocked);
      showSnackbar(t('live_stream.prepare_success'), 'success');
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
      await copyText(grant.public_url, 'live_stream.public_link_copied');
    } catch {
      showSnackbar(t('live_stream.public_link_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleStopTransmission = async () => {
    const code = aisleCode.trim();
    if (!code || !prepared) return;
    const ok = window.confirm(t('live_stream.stop_confirm'));
    if (!ok) return;
    setBusy(true);
    try {
      const result = await stopLiveStream(inventoryId, code);
      setPresence(result.status.presence);
      setPublishBlocked(result.status.publish_blocked);
      showSnackbar(t('live_stream.stop_success'), 'success');
    } catch {
      showSnackbar(t('live_stream.stop_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async () => {
    if (!lastGrantId) return;
    setBusy(true);
    try {
      await revokePublicLiveGrant(inventoryId, lastGrantId);
      setLastGrantId(null);
      setLastPublicUrl(null);
      showSnackbar(t('live_stream.public_link_revoked'), 'success');
    } catch {
      showSnackbar(t('live_stream.public_link_revoke_error'), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
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
        {prepared ? (
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Typography variant="subtitle2">{t('live_stream.rtmp_section')}</Typography>
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
              <Button size="small" onClick={() => void copyText(prepared.rtmp_publish_url, 'live_stream.rtmp_copied')}>
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
            <Typography variant="subtitle2" sx={{ mt: 1 }}>
              {t('live_stream.viewer_section')}
            </Typography>
            <HlsLivePlayer
              playlistUrl={prepared.hls_playlist_url}
              username={prepared.read_username}
              password={prepared.read_password}
              onPresenceChange={(p) => setPresence(p as LiveStreamPresence)}
            />
          </Box>
        ) : null}
        {lastPublicUrl ? (
          <Typography variant="caption" color="text.secondary">
            {t('live_stream.last_public_url')}: {lastPublicUrl}
          </Typography>
        ) : null}
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
        <Button onClick={onClose}>{t('common.close')}</Button>
        <Button onClick={() => void refreshStatus()} disabled={!aisleCode.trim() || busy}>
          {t('live_stream.refresh_status')}
        </Button>
        <Button variant="contained" onClick={() => void handlePrepare()} disabled={!aisleCode.trim() || busy}>
          {t('live_stream.prepare_action')}
        </Button>
        <Button
          onClick={() => void handleStopTransmission()}
          disabled={!prepared || !aisleCode.trim() || busy}
          color="error"
        >
          {t('live_stream.stop_action')}
        </Button>
        <Button onClick={() => void handlePublicLink()} disabled={!aisleCode.trim() || busy}>
          {t('live_stream.public_link_action')}
        </Button>
        <Button onClick={() => void handleRevoke()} disabled={!lastGrantId || busy} color="warning">
          {t('live_stream.revoke_public_link')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}