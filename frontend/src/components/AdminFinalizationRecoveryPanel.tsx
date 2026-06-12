import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import type { JobSummary } from '../api/types';
import { ApiError } from '../api/types';
import {
  postAdminFinalizationRecover,
  type FinalizationRecoveryOperation,
  type AdminFinalizationRecoveryResponse,
} from '../api/adminFinalizationRecoveryApi';
import { resolveApiErrorMessage } from '../utils/apiErrors';

const BLOCKED_ASSESSMENT_OUTCOMES = new Set([
  'complete',
  'failed_before_domain_commit',
  'inconsistent',
]);

const OPERATIONS: FinalizationRecoveryOperation[] = [
  'verify',
  'resume',
  'republish_artifacts',
  'terminalize',
  'promote',
  'reconcile_aisle',
  'reconcile_inventory',
];

export interface AdminFinalizationRecoveryPanelProps {
  job: JobSummary | null;
  isAdmin: boolean;
  onRecovered?: () => Promise<unknown> | void;
}

export default function AdminFinalizationRecoveryPanel({
  job,
  isAdmin,
  onRecovered,
}: AdminFinalizationRecoveryPanelProps) {
  const { t } = useTranslation();
  const [busyOp, setBusyOp] = useState<FinalizationRecoveryOperation | null>(null);
  const [pendingOp, setPendingOp] = useState<FinalizationRecoveryOperation | null>(null);
  const [dryRunPreview, setDryRunPreview] = useState<AdminFinalizationRecoveryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const assessment = job?.finalization_assessment ?? null;
  const assessmentOutcome = String(assessment?.outcome ?? '').toLowerCase();

  const visibleOperations = useMemo((): FinalizationRecoveryOperation[] => {
    if (!assessment) return [];
    if (assessmentOutcome === 'inconsistent') return ['verify'];
    if (BLOCKED_ASSESSMENT_OUTCOMES.has(assessmentOutcome)) return [];
    if (!assessment.recovery_candidate) return ['verify'];
    return OPERATIONS;
  }, [assessment, assessmentOutcome]);

  const runRecovery = useCallback(
    async (operation: FinalizationRecoveryOperation, dryRun: boolean) => {
      if (!job?.id) return;
      setBusyOp(operation);
      setError(null);
      try {
        const response = await postAdminFinalizationRecover(job.id, {
          operation,
          dry_run: dryRun,
        });
        if (dryRun) {
          setDryRunPreview(response);
          setPendingOp(operation);
          return;
        }
        setDryRunPreview(null);
        setPendingOp(null);
        await onRecovered?.();
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        if (err.status === 409) {
          setError(t('jobs.admin_recovery.concurrency_conflict'));
        } else {
          setError(resolveApiErrorMessage(err, 'errors.generic'));
        }
      } finally {
        setBusyOp(null);
      }
    },
    [job?.id, onRecovered, t]
  );

  if (!isAdmin || !job) return null;

  return (
    <Box data-testid="admin-finalization-recovery-panel">
      <Divider sx={{ my: 2 }} />
      <Typography variant="subtitle2" gutterBottom>
        {t('jobs.admin_recovery.title')}
      </Typography>
      {assessmentOutcome === 'failed_before_domain_commit' ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {t('jobs.admin_recovery.full_retry_required')}
        </Alert>
      ) : null}
      {assessment ? (
        <Stack spacing={0.5} sx={{ mb: 1 }}>
          <Typography variant="body2">
            {t('jobs.admin_recovery.outcome')}: {assessment.outcome}
          </Typography>
          <Typography variant="body2">
            {t('jobs.admin_recovery.technical_status')}: {assessment.technical_result_status}
          </Typography>
          <Typography variant="body2">
            {t('jobs.admin_recovery.last_confirmed_stage')}: {assessment.last_confirmed_stage ?? '—'}
          </Typography>
          <Typography variant="body2">
            {t('jobs.admin_recovery.next_required_stage')}: {assessment.next_required_stage ?? '—'}
          </Typography>
          {assessment.blocking_reason ? (
            <Typography variant="body2">
              {t('jobs.admin_recovery.blocking_reason')}: {assessment.blocking_reason}
            </Typography>
          ) : null}
        </Stack>
      ) : null}
      {error ? <Alert severity="warning">{error}</Alert> : null}
      {dryRunPreview ? (
        <Alert severity="info" sx={{ mb: 1 }} data-testid="admin-recovery-dry-run-preview">
          {t('jobs.admin_recovery.dry_run_preview')}: {dryRunPreview.outcome}
        </Alert>
      ) : null}
      <Stack direction="row" flexWrap="wrap" gap={1}>
        {visibleOperations.map((op) => (
          <Button
            key={op}
            size="small"
            variant="outlined"
            disabled={busyOp !== null}
            onClick={() => void runRecovery(op, true)}
            data-testid={`admin-recovery-dry-run-${op}`}
          >
            {op}
          </Button>
        ))}
        {pendingOp ? (
          <Button
            size="small"
            variant="contained"
            color="warning"
            disabled={busyOp !== null}
            onClick={() => void runRecovery(pendingOp, false)}
            data-testid="admin-recovery-confirm"
          >
            {t('jobs.admin_recovery.confirm_action')} ({pendingOp})
          </Button>
        ) : null}
      </Stack>
      {assessmentOutcome === 'inconsistent' ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
          {t('jobs.admin_recovery.verify_only')}
        </Typography>
      ) : null}
    </Box>
  );
}
