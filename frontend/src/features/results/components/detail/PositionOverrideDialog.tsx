import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  createOverride,
  restoreAutomatic,
  type PositionOverrideAction,
  type PositionOverrideReasonCode,
} from '../../../../api/positionOverridesApi';
import { listClientPositionLabels } from '../../../../api/clientPositionLabelsApi';
import { getVisibleErrorMessage } from '../../../../utils/apiErrors';
import type { ResultDetail } from '../../types';

type DialogAction = PositionOverrideAction | 'RESTORE_AUTOMATIC';

const REASON_CODES: readonly PositionOverrideReasonCode[] = [
  'WRONG_POSITION_DETECTED',
  'PRODUCT_MOVED',
  'SEQUENCE_ERROR',
  'POSITION_LABEL_NOT_VISIBLE',
  'POSITION_LABEL_INVALID',
  'AMBIGUOUS_IMAGE',
  'MISSING_POSITION_LABEL',
  'OPERATOR_VERIFICATION',
  'DATA_CORRECTION',
  'OTHER',
];

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `position-override-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface PositionOverrideDialogProps {
  open: boolean;
  inventoryId: string;
  clientId: string;
  result: ResultDetail;
  onClose: () => void;
  onSuccess: () => void | Promise<void>;
}

export default function PositionOverrideDialog({
  open,
  inventoryId,
  clientId,
  result,
  onClose,
  onSuccess,
}: PositionOverrideDialogProps) {
  const { t } = useTranslation();
  const [action, setAction] = useState<DialogAction>('CHANGE_POSITION');
  const [positionLabelId, setPositionLabelId] = useState('');
  const [reasonCode, setReasonCode] =
    useState<PositionOverrideReasonCode>('WRONG_POSITION_DETECTED');
  const [reasonText, setReasonText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const labelsQuery = useQuery({
    queryKey: ['client-position-labels', clientId, 'active', 'position-override'],
    queryFn: () =>
      listClientPositionLabels(clientId, { status: 'active', page: 1, page_size: 200 }),
    enabled: open && Boolean(clientId),
    staleTime: 60_000,
  });

  const labels = useMemo(
    () => (labelsQuery.data?.items ?? []).filter((label) => label.status.toLowerCase() === 'active'),
    [labelsQuery.data?.items]
  );

  useEffect(() => {
    if (!open) return;
    setAction(result.aislePositionId ? 'CHANGE_POSITION' : 'ASSIGN_POSITION');
    setPositionLabelId(result.aislePositionId ?? '');
    setReasonCode('WRONG_POSITION_DETECTED');
    setReasonText('');
    setError(null);
  }, [open, result]);

  const needsPosition = action === 'ASSIGN_POSITION' || action === 'CHANGE_POSITION';
  const expectedVersion = result.positionAssignmentVersion;
  const jobId = result.storageJobId?.trim() ?? '';
  const reasonTextRequired = reasonCode === 'OTHER';
  const valid =
    Boolean(jobId) &&
    expectedVersion != null &&
    (!needsPosition || Boolean(positionLabelId)) &&
    (!reasonTextRequired || Boolean(reasonText.trim()));

  const handleSubmit = async () => {
    if (!valid || expectedVersion == null) return;
    setSubmitting(true);
    setError(null);
    const common = {
      reason_code: reasonCode,
      reason_text: reasonText.trim() || null,
      expected_version: expectedVersion,
      idempotency_key: newIdempotencyKey(),
    };
    try {
      if (action === 'RESTORE_AUTOMATIC') {
        await restoreAutomatic(inventoryId, jobId, result.id, common);
      } else {
        await createOverride(inventoryId, jobId, result.id, {
          ...common,
          action,
          position_label_id: needsPosition ? positionLabelId : null,
        });
      }
      await onSuccess();
      onClose();
    } catch (cause) {
      setError(getVisibleErrorMessage(cause, 'results'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('results.position_override.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {!jobId || expectedVersion == null ? (
            <Alert severity="warning">{t('results.position_override.unavailable')}</Alert>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          <FormControl fullWidth>
            <InputLabel id="position-override-action-label">
              {t('results.position_override.action_label')}
            </InputLabel>
            <Select
              labelId="position-override-action-label"
              value={action}
              label={t('results.position_override.action_label')}
              onChange={(event) => setAction(event.target.value as DialogAction)}
            >
              <MenuItem value="ASSIGN_POSITION">
                {t('results.position_override.actions.assign')}
              </MenuItem>
              <MenuItem value="CHANGE_POSITION">
                {t('results.position_override.actions.change')}
              </MenuItem>
              <MenuItem value="REMOVE_POSITION">
                {t('results.position_override.actions.remove')}
              </MenuItem>
              <MenuItem
                value="RESTORE_AUTOMATIC"
                disabled={!result.manualPositionOverride?.isActive}
              >
                {t('results.position_override.actions.restore')}
              </MenuItem>
            </Select>
          </FormControl>

          {needsPosition ? (
            <FormControl fullWidth disabled={!clientId || labelsQuery.isLoading}>
              <InputLabel id="position-override-label-label">
                {t('results.position_override.position_label')}
              </InputLabel>
              <Select
                labelId="position-override-label-label"
                value={positionLabelId}
                label={t('results.position_override.position_label')}
                onChange={(event) => setPositionLabelId(event.target.value)}
              >
                {labels.map((label) => (
                  <MenuItem key={label.id} value={label.id}>
                    {label.name}
                  </MenuItem>
                ))}
              </Select>
              {labelsQuery.isLoading ? <CircularProgress size={20} sx={{ mt: 1 }} /> : null}
            </FormControl>
          ) : null}

          <FormControl fullWidth>
            <InputLabel id="position-override-reason-label">
              {t('results.position_override.reason_code')}
            </InputLabel>
            <Select
              labelId="position-override-reason-label"
              value={reasonCode}
              label={t('results.position_override.reason_code')}
              onChange={(event) =>
                setReasonCode(event.target.value as PositionOverrideReasonCode)
              }
            >
              {REASON_CODES.map((code) => (
                <MenuItem key={code} value={code}>
                  {t(`results.position_override.reasons.${code}`)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {reasonTextRequired ? (
            <TextField
              required
              multiline
              minRows={2}
              label={t('results.position_override.reason_text')}
              value={reasonText}
              onChange={(event) => setReasonText(event.target.value)}
              inputProps={{ maxLength: 1000 }}
            />
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          {t('common.cancel')}
        </Button>
        <Button variant="contained" onClick={() => void handleSubmit()} disabled={!valid || submitting}>
          {submitting ? t('common.loading') : t('results.position_override.submit')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
