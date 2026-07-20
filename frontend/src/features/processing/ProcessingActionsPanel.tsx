import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Stack, Typography } from '@mui/material';
import { ConfirmDialog, useAppSnackbar } from '../../components/ui';
import { ApiError } from '../../api/types';
import type { AvailableAssetActions, AssetProcessingSummary } from '../../api/types/processing';
import { retryAssetPersistence, sendAssetToExternal } from '../../api/processingApi';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import InvalidateResultDialog from './InvalidateResultDialog';
import ManualResultForm from './ManualResultForm';
import ReprocessDialog from './ReprocessDialog';

export interface ProcessingActionsPanelProps {
  inventoryId: string;
  aisleId: string;
  jobId: string;
  asset: AssetProcessingSummary;
  actions: AvailableAssetActions;
  onActionComplete?: () => void;
}

export default function ProcessingActionsPanel({
  inventoryId,
  aisleId,
  jobId,
  asset,
  actions,
  onActionComplete,
}: ProcessingActionsPanelProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const [invalidateOpen, setInvalidateOpen] = useState(false);
  const [externalConfirmOpen, setExternalConfirmOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<'persistence' | 'external' | null>(null);

  const hasAnyAction =
    actions.can_reprocess ||
    actions.can_retry_persistence ||
    actions.can_send_to_external ||
    actions.can_assign_manual ||
    actions.can_invalidate;

  const runSimpleAction = async (kind: 'persistence' | 'external') => {
    setPendingAction(kind);
    try {
      const body = {
        reason: t('processing.actions.defaultReason'),
        expected_state_version: asset.state_version,
      };
      if (kind === 'persistence') {
        await retryAssetPersistence(inventoryId, aisleId, jobId, asset.asset_id, body);
      } else {
        await sendAssetToExternal(inventoryId, aisleId, jobId, asset.asset_id, body);
      }
      showSnackbar(t('processing.actions.success'), 'success');
      onActionComplete?.();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'processing.actions.failed'), 'error');
    } finally {
      setPendingAction(null);
      setExternalConfirmOpen(false);
    }
  };

  if (!hasAnyAction) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-actions-none">
        {t('processing.actions.none')}
      </Typography>
    );
  }

  return (
    <Box data-testid="processing-actions-panel">
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('processing.actions.title')}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {actions.can_reprocess ? (
          <Button size="small" variant="outlined" onClick={() => setReprocessOpen(true)}>
            {t('processing.actions.reprocess')}
          </Button>
        ) : null}
        {actions.can_retry_persistence ? (
          <Button
            size="small"
            variant="outlined"
            disabled={pendingAction === 'persistence'}
            onClick={() => void runSimpleAction('persistence')}
          >
            {t('processing.actions.retryPersistence')}
          </Button>
        ) : null}
        {actions.can_send_to_external ? (
          <Button size="small" variant="outlined" onClick={() => setExternalConfirmOpen(true)}>
            {t('processing.actions.sendExternal')}
          </Button>
        ) : null}
        {actions.can_assign_manual ? (
          <Button size="small" variant="outlined" onClick={() => setManualOpen(true)}>
            {t('processing.actions.assignManual')}
          </Button>
        ) : null}
        {actions.can_invalidate ? (
          <Button size="small" variant="outlined" color="warning" onClick={() => setInvalidateOpen(true)}>
            {t('processing.actions.invalidate')}
          </Button>
        ) : null}
      </Stack>

      <ReprocessDialog
        open={reprocessOpen}
        onClose={() => setReprocessOpen(false)}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobId={jobId}
        asset={asset}
        onSuccess={() => {
          setReprocessOpen(false);
          onActionComplete?.();
        }}
      />

      <InvalidateResultDialog
        open={invalidateOpen}
        onClose={() => setInvalidateOpen(false)}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobId={jobId}
        asset={asset}
        onSuccess={() => {
          setInvalidateOpen(false);
          onActionComplete?.();
        }}
      />

      <ConfirmDialog
        open={externalConfirmOpen}
        onClose={() => setExternalConfirmOpen(false)}
        title={t('processing.actions.externalConfirmTitle')}
        description={t('processing.actions.externalConfirmDescription', {
          cost:
            asset.estimated_external_cost == null
              ? t('common.em_dash')
              : String(asset.estimated_external_cost),
        })}
        confirmLabel={t('processing.actions.externalConfirmAction')}
        confirmColor="warning"
        loading={pendingAction === 'external'}
        onConfirm={() => runSimpleAction('external')}
      />

      <ManualResultForm
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobId={jobId}
        assetId={asset.asset_id}
        fileName={asset.file_name}
        onSuccess={() => {
          setManualOpen(false);
          onActionComplete?.();
        }}
      />
    </Box>
  );
}
