import ImageOutlinedIcon from '@mui/icons-material/ImageOutlined';
import {
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { formatDate } from '../../../utils/formatDate';
import type {
  CaptureSessionDetailResponse,
  CaptureSessionItemResponse,
} from '../../../types/captureSession';
import ImportSessionUpload from './ImportSessionUpload';
import ImportSessionGroupingPanel from './ImportSessionGroupingPanel';

interface ImportSessionDetailProps {
  detail: CaptureSessionDetailResponse;
  canUpload: boolean;
  canClose: boolean;
  canCancel: boolean;
  closing: boolean;
  cancelling: boolean;
  onCloseSession: () => void;
  onCancelSession: () => void;
  onRefresh: () => void;
}

function sortItemsByEffectiveCaptureTime(items: CaptureSessionItemResponse[]): CaptureSessionItemResponse[] {
  return [...items].sort((a, b) => {
    const t1 = a.effective_capture_time ? new Date(a.effective_capture_time).getTime() : Number.POSITIVE_INFINITY;
    const t2 = b.effective_capture_time ? new Date(b.effective_capture_time).getTime() : Number.POSITIVE_INFINITY;
    if (t1 !== t2) return t1 - t2;
    return a.id.localeCompare(b.id);
  });
}

function importStatusChip(
  item: CaptureSessionItemResponse,
  t: (key: string) => string
): { label: string; color: 'default' | 'success' | 'error' | 'warning' } {
  if (item.import_status === 'import_failed') {
    return { label: t('ingestion_sessions.detail.import_status_failed'), color: 'error' };
  }
  if (item.import_status === 'pending_import' || item.import_status === 'importing') {
    return { label: t('ingestion_sessions.detail.import_status_pending'), color: 'warning' };
  }
  if (item.import_status === 'imported') {
    return { label: t('ingestion_sessions.detail.import_status_imported'), color: 'success' };
  }
  return { label: item.import_status, color: 'default' };
}

export default function ImportSessionDetail({
  detail,
  canUpload,
  canClose,
  canCancel,
  closing,
  cancelling,
  onCloseSession,
  onCancelSession,
  onRefresh,
}: ImportSessionDetailProps) {
  const { t } = useTranslation();
  const sortedItems = useMemo(() => sortItemsByEffectiveCaptureTime(detail.items), [detail.items]);
  const noItems = sortedItems.length === 0;
  const ungroupedCount = useMemo(
    () => detail.items.filter((i) => i.group_id == null || i.group_id === '').length,
    [detail.items]
  );

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6">{t('ingestion_sessions.detail.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('ingestion_sessions.detail.session_id')}: {detail.session.id}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('ingestion_sessions.detail.status')}: {detail.session.status}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('ingestion_sessions.detail.created')}: {formatDate(detail.session.created_at)}
        </Typography>
      </Box>

      <Divider />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Button variant="contained" onClick={onCloseSession} disabled={!canClose || closing}>
          {t('ingestion_sessions.actions.close_session')}
        </Button>
        <Button variant="outlined" color="error" onClick={onCancelSession} disabled={!canCancel || cancelling}>
          {t('ingestion_sessions.actions.cancel_session')}
        </Button>
      </Stack>

      <ImportSessionUpload
        inventoryId={detail.session.inventory_id}
        aisleId={detail.session.aisle_id ?? undefined}
        sessionId={detail.session.id}
        disabled={!canUpload}
        onCompleted={onRefresh}
      />

      <Divider />

      <ImportSessionGroupingPanel
        inventoryId={detail.session.inventory_id}
        sessionId={detail.session.id}
        session={detail.session}
        ungroupedCount={ungroupedCount}
        onRefresh={onRefresh}
      />

      <Divider />

      {noItems ? (
        <Typography color="text.secondary">{t('ingestion_sessions.empty.upload_to_begin')}</Typography>
      ) : (
        <List dense>
          {sortedItems.map((item) => {
            const chip = importStatusChip(item, t);
            return (
              <ListItem key={item.id} divider alignItems="flex-start">
                <ListItemAvatar>
                  <Avatar variant="rounded">
                    <ImageOutlinedIcon />
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Typography component="span" variant="body2">
                        {item.original_filename || item.staging_storage_key}
                      </Typography>
                      <Chip size="small" label={chip.label} color={chip.color} variant="outlined" />
                    </Box>
                  }
                  secondary={
                    <Box component="span" sx={{ display: 'block' }}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {t('ingestion_sessions.detail.effective_capture_time')}:{' '}
                        {item.effective_capture_time
                          ? formatDate(item.effective_capture_time)
                          : t('ingestion_sessions.common.not_available')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {t('ingestion_sessions.detail.time_source')}:{' '}
                        {item.time_source
                          ? t(`ingestion_sessions.detail.time_source_values.${item.time_source}`)
                          : t('ingestion_sessions.common.not_available')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        {t('ingestion_sessions.detail.time_confidence')}:{' '}
                        {typeof item.time_confidence === 'number'
                          ? item.time_confidence.toFixed(2)
                          : t('ingestion_sessions.common.not_available')}
                      </Typography>
                      {item.import_status === 'import_failed' && (item.last_error_code || item.last_error_detail) ? (
                        <Typography variant="caption" color="error.main" display="block">
                          {item.last_error_code ? `${item.last_error_code}: ` : ''}
                          {item.last_error_detail ?? ''}
                        </Typography>
                      ) : null}
                    </Box>
                  }
                />
              </ListItem>
            );
          })}
        </List>
      )}
    </Stack>
  );
}
