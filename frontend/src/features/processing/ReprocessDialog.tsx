import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, FormControl, InputLabel, MenuItem, Select, TextField } from '@mui/material';
import { ConfirmDialog, useAppSnackbar } from '../../components/ui';
import { ApiError } from '../../api/types';
import type { AssetProcessingSummary } from '../../api/types/processing';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { useReprocessAsset } from './hooks/useReprocessAsset';

const STRATEGY_OPTIONS = ['INTERNAL', 'EXTERNAL', 'CODE_SCAN', 'INTERNAL_OCR'] as const;

export interface ReprocessDialogProps {
  open: boolean;
  onClose: () => void;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  asset: AssetProcessingSummary;
  onSuccess?: () => void;
}

export default function ReprocessDialog({
  open,
  onClose,
  inventoryId,
  aisleId,
  jobId,
  asset,
  onSuccess,
}: ReprocessDialogProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [strategy, setStrategy] = useState('');
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const mutation = useReprocessAsset(inventoryId, aisleId, jobId, asset.asset_id);

  useEffect(() => {
    if (!open) return;
    setStrategy(asset.executed_strategy ?? '');
    setReason('');
    setReasonError('');
    setSubmitError(null);
  }, [open, asset.asset_id, asset.executed_strategy]);

  const handleConfirm = async () => {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setReasonError(t('processing.reprocess.reasonRequired'));
      return;
    }
    setReasonError('');
    setSubmitError(null);
    try {
      await mutation.mutateAsync({
        reason: trimmedReason,
        expected_state_version: asset.state_version,
        strategy: strategy || undefined,
      });
      showSnackbar(t('processing.reprocess.success'), 'success');
      onSuccess?.();
      onClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setSubmitError(resolveApiErrorMessage(err, 'processing.reprocess.failed'));
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      title={t('processing.reprocess.title')}
      description={
        <>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t('processing.reprocess.costWarning', {
              cost:
                asset.estimated_external_cost == null
                  ? t('common.em_dash')
                  : String(asset.estimated_external_cost),
            })}
          </Alert>
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel id="reprocess-strategy-label">{t('processing.reprocess.strategy')}</InputLabel>
            <Select
              labelId="reprocess-strategy-label"
              label={t('processing.reprocess.strategy')}
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              data-testid="reprocess-strategy-select"
            >
              <MenuItem value="">{t('processing.reprocess.strategyDefault')}</MenuItem>
              {STRATEGY_OPTIONS.map((option) => (
                <MenuItem key={option} value={option}>
                  {option}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label={t('processing.reprocess.reason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={Boolean(reasonError)}
            helperText={reasonError || t('processing.reprocess.reasonHint')}
            fullWidth
            multiline
            minRows={2}
            inputProps={{ 'data-testid': 'reprocess-reason-input' }}
          />
          {submitError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {submitError}
            </Alert>
          ) : null}
        </>
      }
      confirmLabel={t('processing.reprocess.confirm')}
      confirmColor="warning"
      loading={mutation.isPending}
      onConfirm={() => void handleConfirm()}
    />
  );
}
