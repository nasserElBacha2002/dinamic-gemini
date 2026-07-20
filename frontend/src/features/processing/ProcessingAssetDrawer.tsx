import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Divider,
  Drawer,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { DrawerHeader, ErrorAlert, LoadingBlock, StatusBadge } from '../../components/ui';
import type { AssetProcessingDetail } from '../../api/types/processing';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import ProcessingActionsPanel from './ProcessingActionsPanel';
import ProcessingAttemptTimeline from './ProcessingAttemptTimeline';
import ProcessingEvidencePanel from './ProcessingEvidencePanel';
import ProcessingLogsTimeline from './ProcessingLogsTimeline';
import {
  processingErrorCodeMessage,
  processingStatusLabel,
  processingStatusToSemantic,
  shortAssetId,
} from './utils/processingStatus';

export interface ProcessingAssetDrawerProps {
  open: boolean;
  onClose: () => void;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  detail: AssetProcessingDetail | null | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry?: () => void;
  onRefresh?: () => void;
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '130px 1fr', gap: 0.5 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" sx={{ wordBreak: 'break-word' }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function ProcessingAssetDrawer({
  open,
  onClose,
  inventoryId,
  aisleId,
  jobId,
  detail,
  isLoading,
  error,
  onRetry,
  onRefresh,
}: ProcessingAssetDrawerProps) {
  const { t } = useTranslation();
  const contentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      const timer = window.setTimeout(() => contentRef.current?.focus(), 0);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [open, detail?.asset.asset_id]);

  const asset = detail?.asset;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: '100%', md: 520, lg: 640 } } }}
    >
      <DrawerHeader
        title={
          <Typography variant="h6" component="h2">
            {asset?.file_name || (asset ? shortAssetId(asset.asset_id) : t('processing.drawer.title'))}
          </Typography>
        }
        subtitle={
          asset ? (
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <StatusBadge
                label={processingStatusLabel(asset.status, t)}
                semantic={processingStatusToSemantic(asset.status)}
              />
              {asset.last_error_code ? (
                <Typography variant="caption" color="error">
                  {processingErrorCodeMessage(asset.last_error_code, t)}
                </Typography>
              ) : null}
            </Stack>
          ) : undefined
        }
        onClose={onClose}
        closeLabel={t('common.close')}
      />

      <Box
        ref={contentRef}
        tabIndex={-1}
        sx={{ p: 2.5, overflow: 'auto', outline: 'none' }}
        data-testid="processing-asset-drawer"
      >
        {isLoading ? <LoadingBlock message={t('processing.drawer.loading')} py={4} /> : null}
        {!isLoading && error ? (
          <ErrorAlert
            message={resolveApiErrorMessage(error, 'processing.drawer.loadFailed')}
            onRetry={onRetry}
          />
        ) : null}

        {!isLoading && !error && detail?.historical_incomplete ? (
          <Alert severity="info" sx={{ mb: 2 }} data-testid="processing-drawer-historical">
            {t('processing.drawer.historicalUnavailable')}
          </Alert>
        ) : null}

        {!isLoading && !error && asset ? (
          <Stack spacing={2.5}>
            <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="processing-drawer-summary">
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('processing.drawer.summarySection')}
              </Typography>
              <Stack spacing={0.75}>
                <MetadataRow
                  label={t('processing.drawer.resolvedBy')}
                  value={asset.resolved_by || t('common.em_dash')}
                />
                <MetadataRow
                  label={t('processing.drawer.strategy')}
                  value={asset.executed_strategy || t('common.em_dash')}
                />
                <MetadataRow
                  label={t('processing.drawer.mode')}
                  value={asset.requested_mode || t('common.em_dash')}
                />
                <MetadataRow
                  label={t('processing.drawer.result')}
                  value={
                    asset.internal_code
                      ? `${asset.internal_code}${asset.quantity != null ? ` × ${asset.quantity}` : ''}`
                      : t('common.em_dash')
                  }
                />
                <MetadataRow
                  label={t('processing.drawer.attempts')}
                  value={String(asset.attempt_count)}
                />
                <MetadataRow
                  label={t('processing.drawer.persistence')}
                  value={asset.persistence_status || t('common.em_dash')}
                />
              </Stack>
            </Paper>

            <Box data-testid="processing-drawer-attempts-section">
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('processing.drawer.attemptsSection')}
              </Typography>
              <ProcessingAttemptTimeline
                attempts={detail.attempts}
                historicalIncomplete={detail.historical_incomplete}
              />
            </Box>

            <Box data-testid="processing-drawer-evidence-section">
              <ProcessingEvidencePanel
                asset={asset}
                inventoryId={inventoryId}
                aisleId={aisleId}
                jobId={jobId}
                canViewSensitiveEvidence={detail.available_actions.can_view_sensitive_evidence}
                active={open}
              />
            </Box>

            <Box data-testid="processing-drawer-logs-section">
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('processing.drawer.logsSection')}
              </Typography>
              <ProcessingLogsTimeline
                events={(detail.events ?? []).map((event, index) => ({
                  id: String(event.id ?? `event-${index}`),
                  event_type: String(event.event_type ?? 'event'),
                  timestamp: String(event.timestamp ?? event.created_at ?? ''),
                  level: typeof event.level === 'string' ? event.level : null,
                  message: typeof event.message === 'string' ? event.message : null,
                  metadata:
                    event.metadata && typeof event.metadata === 'object'
                      ? (event.metadata as Record<string, unknown>)
                      : null,
                }))}
              />
            </Box>

            <Divider />

            <ProcessingActionsPanel
              inventoryId={inventoryId}
              aisleId={aisleId}
              jobId={jobId}
              asset={asset}
              actions={detail.available_actions}
              onActionComplete={onRefresh}
            />
          </Stack>
        ) : null}
      </Box>
    </Drawer>
  );
}
