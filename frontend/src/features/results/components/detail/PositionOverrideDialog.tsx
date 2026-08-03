import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Autocomplete,
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
import {
  listClientPositionLabels,
  type ClientPositionLabel,
} from '../../../../api/clientPositionLabelsApi';
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

function commandFingerprint(args: {
  action: DialogAction;
  positionLabelId: string;
  reasonCode: PositionOverrideReasonCode;
  reasonText: string;
  expectedVersion: number | null | undefined;
}): string {
  return [
    args.action,
    args.positionLabelId,
    args.reasonCode,
    args.reasonText.trim(),
    String(args.expectedVersion ?? ''),
  ].join('|');
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
  const [selectedLabel, setSelectedLabel] = useState<ClientPositionLabel | null>(
    null
  );
  const [labelSearch, setLabelSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [reasonCode, setReasonCode] =
    useState<PositionOverrideReasonCode>('WRONG_POSITION_DETECTED');
  const [reasonText, setReasonText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey());
  const lastFingerprintRef = useRef<string>('');

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(labelSearch.trim()), 250);
    return () => window.clearTimeout(handle);
  }, [labelSearch]);

  const labelsQuery = useQuery({
    queryKey: [
      'client-position-labels',
      clientId,
      'active',
      'position-override-search',
      debouncedSearch,
    ],
    queryFn: () =>
      listClientPositionLabels(clientId, {
        status: 'active',
        page: 1,
        page_size: 50,
        search: debouncedSearch || null,
      }),
    enabled: open && Boolean(clientId),
    staleTime: 30_000,
  });

  const labels = useMemo(
    () =>
      (labelsQuery.data?.items ?? []).filter(
        (label) => label.status.toLowerCase() === 'active'
      ),
    [labelsQuery.data?.items]
  );

  useEffect(() => {
    if (!open) return;
    setAction(result.aislePositionId ? 'CHANGE_POSITION' : 'ASSIGN_POSITION');
    setSelectedLabel(
      result.aislePositionId
        ? ({
            id: result.aislePositionId,
            public_identifier: result.aislePositionId,
            name: result.aislePositionName ?? result.aislePositionId,
            description: null,
            status: 'active',
            client_id: clientId,
            created_at: '',
            updated_at: '',
            available_formats: [],
          } satisfies ClientPositionLabel)
        : null
    );
    setLabelSearch('');
    setDebouncedSearch('');
    setReasonCode('WRONG_POSITION_DETECTED');
    setReasonText('');
    setError(null);
    setIdempotencyKey(newIdempotencyKey());
    lastFingerprintRef.current = '';
  }, [open, result, clientId]);

  const needsPosition = action === 'ASSIGN_POSITION' || action === 'CHANGE_POSITION';
  const expectedVersion = result.positionAssignmentVersion;
  const jobId = result.storageJobId?.trim() ?? '';
  const reasonTextRequired = reasonCode === 'OTHER';
  const positionLabelId = selectedLabel?.id ?? '';
  const fingerprint = commandFingerprint({
    action,
    positionLabelId,
    reasonCode,
    reasonText,
    expectedVersion,
  });

  useEffect(() => {
    if (!open) return;
    if (!lastFingerprintRef.current) {
      lastFingerprintRef.current = fingerprint;
      return;
    }
    if (lastFingerprintRef.current !== fingerprint) {
      lastFingerprintRef.current = fingerprint;
      setIdempotencyKey(newIdempotencyKey());
    }
  }, [fingerprint, open]);

  const valid =
    Boolean(jobId) &&
    expectedVersion != null &&
    (!needsPosition || Boolean(positionLabelId)) &&
    (!reasonTextRequired || Boolean(reasonText.trim()));

  const handleSubmit = async () => {
    if (!valid || expectedVersion == null || submitting) return;
    setSubmitting(true);
    setError(null);
    const common = {
      reason_code: reasonCode,
      reason_text: reasonText.trim() || null,
      expected_version: expectedVersion,
      idempotency_key: idempotencyKey,
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
      setIdempotencyKey(newIdempotencyKey());
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
              disabled={submitting}
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
            <Autocomplete
              options={labels}
              loading={labelsQuery.isLoading || labelsQuery.isFetching}
              value={selectedLabel}
              onChange={(_event, value) => setSelectedLabel(value)}
              inputValue={labelSearch}
              onInputChange={(_event, value, reason) => {
                if (reason === 'input' || reason === 'clear') {
                  setLabelSearch(value);
                }
              }}
              getOptionLabel={(option) => option.name}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              disabled={!clientId || submitting}
              noOptionsText={t('results.position_override.no_labels')}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('results.position_override.position_label')}
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {labelsQuery.isFetching ? (
                          <CircularProgress color="inherit" size={16} />
                        ) : null}
                        {params.InputProps.endAdornment}
                      </>
                    ),
                  }}
                />
              )}
            />
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
              disabled={submitting}
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
              disabled={submitting}
            />
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          {t('common.cancel')}
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleSubmit()}
          disabled={!valid || submitting}
        >
          {submitting ? t('common.loading') : t('results.position_override.submit')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
