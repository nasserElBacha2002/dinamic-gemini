import { useState } from 'react';
import { Box, Button, Chip, Stack, Typography } from '@mui/material';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import { useTranslation } from 'react-i18next';
import type { LiveStreamChannelSummary } from '../../api/liveStreamApi';
import { prepareLiveStream, stopLiveStream } from '../../api/liveStreamApi';
import { useAppSnackbar } from '../../components/ui';
import { isPublisherActivePresence } from './liveStreamPresence';

export interface InventoryLiveStreamBarProps {
  inventoryId: string;
  channels: LiveStreamChannelSummary[];
  onPrepare: () => void;
  onManage: (aisleCode: string) => void;
  onChannelsChanged: () => void;
}

export default function InventoryLiveStreamBar({
  inventoryId,
  channels,
  onPrepare,
  onManage,
  onChannelsChanged,
}: InventoryLiveStreamBarProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [busyAisle, setBusyAisle] = useState<string | null>(null);

  const activeChannels = channels.filter((ch) => isPublisherActivePresence(ch.status.presence));

  const handleRehabilitate = async (aisleCode: string) => {
    setBusyAisle(aisleCode);
    try {
      await prepareLiveStream(inventoryId, aisleCode);
      showSnackbar(t('live_stream.rehabilitate_success'), 'success');
      onChannelsChanged();
    } catch {
      showSnackbar(t('live_stream.prepare_error'), 'error');
    } finally {
      setBusyAisle(null);
    }
  };

  const handleStop = async (aisleCode: string) => {
    const ok = window.confirm(t('live_stream.stop_confirm'));
    if (!ok) return;
    setBusyAisle(aisleCode);
    try {
      await stopLiveStream(inventoryId, aisleCode);
      showSnackbar(t('live_stream.stop_success'), 'success');
      onChannelsChanged();
    } catch {
      showSnackbar(t('live_stream.stop_error'), 'error');
    } finally {
      setBusyAisle(null);
    }
  };

  if (channels.length === 0) {
    return (
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
        <Button variant="outlined" size="small" onClick={onPrepare} data-testid="inventory-live-prepare">
          {t('live_stream.inventory_prepare')}
        </Button>
      </Box>
    );
  }

  return (
    <Stack spacing={1} data-testid="inventory-live-stream-bar">
      {activeChannels.length === 0 ? (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            {t('live_stream.inventory_prepared_channels')}
          </Typography>
          <Button variant="outlined" size="small" onClick={onPrepare}>
            {t('live_stream.inventory_prepare')}
          </Button>
        </Box>
      ) : null}
      {channels.map((ch) => {
        const live = isPublisherActivePresence(ch.status.presence);
        const blocked = ch.status.publish_blocked;
        const busy = busyAisle === ch.aisle_code;
        return (
          <Box
            key={ch.channel_slug}
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 1,
              alignItems: 'center',
              py: 0.5,
            }}
          >
            {live ? (
              <Chip
                size="small"
                color="error"
                icon={<FiberManualRecordIcon sx={{ fontSize: 12 }} />}
                label={t('live_stream.inventory_live_badge', { aisle: ch.aisle_code })}
              />
            ) : blocked ? (
              <Typography variant="body2" color="warning.main">
                {t('live_stream.inventory_blocked_badge', { aisle: ch.aisle_code })}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t('live_stream.inventory_channel_status', {
                  aisle: ch.aisle_code,
                  status: t(`live_stream.presence_${ch.status.presence}`),
                })}
              </Typography>
            )}
            <Button size="small" onClick={() => onManage(ch.aisle_code)} disabled={busy}>
              {t('live_stream.inventory_manage')}
            </Button>
            {blocked ? (
              <Button
                size="small"
                variant="contained"
                disabled={busy}
                onClick={() => void handleRehabilitate(ch.aisle_code)}
                data-testid="inventory-live-rehabilitate"
              >
                {t('live_stream.rehabilitate_action')}
              </Button>
            ) : (
              <Button size="small" color="error" disabled={busy} onClick={() => void handleStop(ch.aisle_code)}>
                {t('live_stream.stop_action')}
              </Button>
            )}
          </Box>
        );
      })}
    </Stack>
  );
}