import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, TextField } from '@mui/material';
import { ConfirmDialog, useAppSnackbar } from '../../components/ui';
import { ApiError } from '../../api/types';
import type { AssetProcessingSummary } from '../../api/types/processing';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { useInvalidateResult } from './hooks/useInvalidateResult';

export interface InvalidateResultDialogProps {
  open: boolean;
  onClose: () => void;
  inventoryId: string;
  aisleId: string;
  jobId: string;
  asset: AssetProcessingSummary;
  onSuccess?: () => void;
}

export default function InvalidateResultDialog({
  open,
  onClose,
  inventoryId,
  aisleId,
  jobId,
  asset,
  onSuccess,
}: InvalidateResultDialogProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const mutation = useInvalidateResult(inventoryId, aisleId, jobId, asset.asset_id);

  useEffect(() => {
    if (!open) return;
    setReason('');
    setReasonError('');
    setSubmitError(null);
    setIdempotencyKey(
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `invalidate-${Date.now()}`
    );
  }, [open, asset.asset_id]);

  const handleConfirm = async () => {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setReasonError(t('processing.invalidate.reasonRequired'));
      return;
    }
    setReasonError('');
    setSubmitError(null);
    try {
      await mutation.mutateAsync({
        reason: trimmedReason,
        expected_state_version: asset.state_version,
        idempotencyKey,
      });
      showSnackbar(t('processing.invalidate.success'), 'success');
      onSuccess?.();
      onClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      if (err.status === 409) {
        setSubmitError(resolveApiErrorMessage(err, 'processing.invalidate.conflict'));
        onSuccess?.();
        return;
      }
      setSubmitError(resolveApiErrorMessage(err, 'processing.invalidate.failed'));
    }
  };

  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      title={t('processing.invalidate.title')}
      description={
        <>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {t('processing.invalidate.warning')}
          </Alert>
          <TextField
            label={t('processing.invalidate.reason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={Boolean(reasonError)}
            helperText={reasonError || t('processing.invalidate.reasonHint')}
            fullWidth
            multiline
            minRows={2}
            inputProps={{ 'data-testid': 'invalidate-reason-input' }}
          />
          {submitError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {submitError}
            </Alert>
          ) : null}
        </>
      }
      confirmLabel={t('processing.invalidate.confirm')}
      confirmColor="error"
      loading={mutation.isPending}
      onConfirm={() => void handleConfirm()}
    />
  );
}
