/**
 * Unified aisle observability: merged execution logs, per-job log, job metadata, downloads.
 * Single dialog — no nested modals.
 */

import { useCallback, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { ExecutionLogEvent, JobSummary } from '../api/types';
import { ApiError } from '../api/types';
import {
  downloadAisleExecutionLogTxt,
  downloadExecutionLogTxt,
} from '../api/client';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../utils/jobStatus';
import { resolveDisplayFinishedAt } from '../utils/jobDisplayTimestamps';
import ExecutionLogPanel from './ExecutionLogPanel';
import { ErrorAlert, StatusBadge, useAppSnackbar } from './ui';
import {
  useAisleExecutionLog,
  useAisleJobDetail,
  useAisleJobsList,
  useCancelAisleJob,
  useExecutionLog,
  useRetryAisleJob,
} from '../hooks';

/** Matches backend aggregate cap for aisle execution logs. */
const AISLE_OBSERVABILITY_JOBS_LIMIT = 500;

function formatOptionalDate(value?: string | null): string {
  return value ? formatDate(value) : '—';
}

function canCancelJob(status?: string | null): boolean {
  const normalized = String(status ?? '').toLowerCase();
  return normalized === 'starting' || normalized === 'running';
}

function isCancelRequested(status?: string | null): boolean {
  return String(status ?? '').toLowerCase() === 'cancel_requested';
}

function canRetryJob(status?: string | null): boolean {
  const normalized = String(status ?? '').toLowerCase();
  return normalized === 'failed' || normalized === 'canceled';
}

function shortJobId(id: string): string {
  const s = id.trim();
  if (s.length <= 14) return s;
  return `${s.slice(0, 8)}…${s.slice(-4)}`;
}

function jobOptionLabel(job: JobSummary): string {
  const head = [job.provider_name, job.model_name]
    .filter((x) => x != null && String(x).trim() !== '')
    .join(' · ');
  if (head) return `${head} · ${shortJobId(job.id)}`;
  return shortJobId(job.id);
}

function jobMetadataRows(
  job: JobSummary | null | undefined,
  executionLogEvents?: ExecutionLogEvent[] | null
): Array<{ label: string; value: string }> {
  if (!job) return [];
  const displayFinished = resolveDisplayFinishedAt(job, executionLogEvents);
  return [
    { label: 'Started', value: formatOptionalDate(job.started_at) },
    { label: 'Finished', value: formatOptionalDate(displayFinished) },
    { label: 'Last heartbeat', value: formatOptionalDate(job.last_heartbeat_at) },
    { label: 'Cancellation requested', value: formatOptionalDate(job.cancel_requested_at) },
    { label: 'Current stage', value: job.current_stage || '—' },
    { label: 'Current step', value: job.current_substep || '—' },
    { label: 'Step started', value: formatOptionalDate(job.current_step_started_at) },
    { label: 'Execution ID', value: job.execution_id || '—' },
    { label: 'Provider', value: job.provider_name || '—' },
    { label: 'Model', value: job.model_name || '—' },
    { label: 'Prompt key', value: job.prompt_key || '—' },
    { label: 'Prompt version', value: job.prompt_version || '—' },
    { label: 'Attempt', value: job.attempt_count ? `Attempt ${job.attempt_count}` : '—' },
    { label: 'Retry of job', value: job.retry_of_job_id || '—' },
    { label: 'Failure code', value: job.failure_code || '—' },
    { label: 'Failure message', value: job.failure_message || job.error_message || '—' },
  ];
}

export interface AisleObservabilityDialogProps {
  open: boolean;
  inventoryId: string;
  aisleId: string;
  aisleCode: string;
  /** When opening from a job row action, pre-select that job and job-scope log. */
  initialSelectedJobId: string | null;
  onClose: () => void;
  /** Refetch parent aisles table after job mutations (cancel/retry). */
  onAislesInvalidate?: () => Promise<unknown>;
}

type LogScope = 'merged' | 'job';

export default function AisleObservabilityDialog({
  open,
  inventoryId,
  aisleId,
  aisleCode,
  initialSelectedJobId,
  onClose,
  onAislesInvalidate,
}: AisleObservabilityDialogProps) {
  const { showSnackbar } = useAppSnackbar();
  const [logScope, setLogScope] = useState<LogScope>(() => (initialSelectedJobId ? 'job' : 'merged'));
  const [selectedJobId, setSelectedJobId] = useState<string>(() => initialSelectedJobId ?? '');

  const aisleExecutionLogQuery = useAisleExecutionLog(inventoryId, aisleId, {
    enabled: open && Boolean(inventoryId && aisleId),
  });
  const jobsListQuery = useAisleJobsList(inventoryId, aisleId, {
    enabled: open && Boolean(inventoryId && aisleId),
    limit: AISLE_OBSERVABILITY_JOBS_LIMIT,
  });
  const jobDetailQuery = useAisleJobDetail(inventoryId, aisleId, selectedJobId || undefined, {
    enabled: open && Boolean(inventoryId && aisleId && selectedJobId),
  });
  const executionLogQuery = useExecutionLog(inventoryId, aisleId, selectedJobId || undefined, {
    enabled: open && Boolean(inventoryId && aisleId && selectedJobId) && logScope === 'job',
  });

  const cancelJobMutation = useCancelAisleJob(inventoryId);
  const retryJobMutation = useRetryAisleJob(inventoryId);

  const [downloadingMerged, setDownloadingMerged] = useState(false);
  const [downloadingJobLog, setDownloadingJobLog] = useState(false);

  const selectedJob = jobDetailQuery.data ?? null;
  const jobs = jobsListQuery.data?.jobs ?? [];

  const executionEventsForFinished = logScope === 'job' ? executionLogQuery.data?.events : null;

  const panelLog = logScope === 'merged' ? aisleExecutionLogQuery.data ?? null : executionLogQuery.data ?? null;
  const panelLoading = logScope === 'merged' ? aisleExecutionLogQuery.isLoading : executionLogQuery.isLoading;
  const panelError = logScope === 'merged' ? aisleExecutionLogQuery.error : executionLogQuery.error;
  const panelEmptyMessage =
    logScope === 'merged'
      ? 'No execution log entries found for any job on this aisle.'
      : selectedJobId
        ? 'No log entries yet for this job, or the log file is not available.'
        : 'Select a job to load this job’s execution log.';

  const refreshBusy =
    aisleExecutionLogQuery.isFetching ||
    jobsListQuery.isFetching ||
    (selectedJobId ? jobDetailQuery.isFetching || (logScope === 'job' && executionLogQuery.isFetching) : false);

  const handleRefresh = useCallback(async () => {
    const tasks: Promise<unknown>[] = [
      aisleExecutionLogQuery.refetch(),
      jobsListQuery.refetch(),
    ];
    if (selectedJobId) {
      tasks.push(jobDetailQuery.refetch());
      if (logScope === 'job') tasks.push(executionLogQuery.refetch());
    }
    await Promise.all(tasks);
    await onAislesInvalidate?.();
  }, [
    aisleExecutionLogQuery,
    executionLogQuery,
    jobDetailQuery,
    jobsListQuery,
    logScope,
    onAislesInvalidate,
    selectedJobId,
  ]);

  const handleCancelJob = async () => {
    if (!selectedJobId) return;
    try {
      await cancelJobMutation.mutateAsync({ aisleId, jobId: selectedJobId });
      showSnackbar('Cancellation requested', 'success');
      await handleRefresh();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(getApiErrorMessage(err, 'Failed to cancel job'), 'error');
    }
  };

  const handleRetryJob = async () => {
    if (!selectedJobId) return;
    try {
      const result = await retryJobMutation.mutateAsync({ aisleId, jobId: selectedJobId });
      setSelectedJobId(result.id);
      setLogScope('job');
      showSnackbar(`Retry started as attempt ${result.attempt_count ?? 'new'}`, 'success');
      await Promise.all([
        onAislesInvalidate?.(),
        aisleExecutionLogQuery.refetch(),
        jobsListQuery.refetch(),
      ]);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(getApiErrorMessage(err, 'Failed to retry job'), 'error');
    }
  };

  const onJobSelectChange = (value: string) => {
    if (!value) {
      setSelectedJobId('');
      setLogScope('merged');
      return;
    }
    setSelectedJobId(value);
    setLogScope('job');
  };

  const onScopeChange = (scope: LogScope) => {
    setLogScope(scope);
    if (scope === 'merged' && !selectedJobId) {
      /* keep */
    }
    if (scope === 'job' && !selectedJobId) {
      /* panel shows empty message until user picks a job */
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      <DialogTitle>Aisle observability — {aisleCode}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 1,
              alignItems: 'center',
              justifyContent: 'flex-end',
            }}
          >
            <Button size="small" variant="outlined" onClick={() => void handleRefresh()} disabled={refreshBusy}>
              {refreshBusy ? 'Refreshing…' : 'Refresh'}
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={!inventoryId || downloadingMerged}
              onClick={async () => {
                setDownloadingMerged(true);
                try {
                  await downloadAisleExecutionLogTxt(inventoryId, aisleId);
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(getApiErrorMessage(err, 'Failed to download merged log'), 'error');
                } finally {
                  setDownloadingMerged(false);
                }
              }}
            >
              {downloadingMerged ? 'Downloading…' : 'Download merged log'}
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={!inventoryId || !selectedJobId || downloadingJobLog}
              onClick={async () => {
                if (!selectedJobId) return;
                setDownloadingJobLog(true);
                try {
                  await downloadExecutionLogTxt(inventoryId, aisleId, selectedJobId);
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(getApiErrorMessage(err, 'Failed to download job log'), 'error');
                } finally {
                  setDownloadingJobLog(false);
                }
              }}
            >
              {downloadingJobLog ? 'Downloading…' : 'Download selected job log'}
            </Button>
            {selectedJobId ? (
              <>
                {isCancelRequested(selectedJob?.status) ? (
                  <Button size="small" variant="outlined" disabled>
                    Cancellation requested
                  </Button>
                ) : null}
                {canCancelJob(selectedJob?.status) ? (
                  <Button
                    size="small"
                    variant="outlined"
                    color="warning"
                    onClick={() => void handleCancelJob()}
                    disabled={cancelJobMutation.isPending}
                  >
                    {cancelJobMutation.isPending ? 'Cancelling…' : 'Cancel job'}
                  </Button>
                ) : null}
                {canRetryJob(selectedJob?.status) ? (
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => void handleRetryJob()}
                    disabled={retryJobMutation.isPending}
                  >
                    {retryJobMutation.isPending ? 'Retrying…' : 'Retry job'}
                  </Button>
                ) : null}
              </>
            ) : null}
          </Box>

          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              gap: 2,
              alignItems: 'stretch',
            }}
          >
            <Box
              sx={{
                flex: { md: '0 0 280px' },
                minWidth: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: 1.5,
              }}
            >
              <FormControl size="small" fullWidth>
                <InputLabel id="obs-scope-label">Log scope</InputLabel>
                <Select
                  labelId="obs-scope-label"
                  label="Log scope"
                  value={logScope}
                  onChange={(e) => onScopeChange(e.target.value as LogScope)}
                >
                  <MenuItem value="merged">Merged aisle log</MenuItem>
                  <MenuItem value="job">Selected job log</MenuItem>
                </Select>
              </FormControl>

              <FormControl size="small" fullWidth>
                <InputLabel id="obs-job-label">Job</InputLabel>
                <Select
                  labelId="obs-job-label"
                  label="Job"
                  value={selectedJobId}
                  onChange={(e) => onJobSelectChange(e.target.value)}
                  disabled={jobsListQuery.isLoading}
                >
                  <MenuItem value="">
                    <em>None (merged only)</em>
                  </MenuItem>
                  {jobs.map((j) => (
                    <MenuItem key={j.id} value={j.id}>
                      {jobOptionLabel(j)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {selectedJobId ? (
                <Paper variant="outlined" sx={{ p: 1.25, maxHeight: 240, overflow: 'auto' }}>
                  <Stack spacing={1}>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, alignItems: 'center' }}>
                      {selectedJob ? (
                        <StatusBadge
                          label={getJobStatusLabel(selectedJob.status)}
                          semantic={jobStatusToBadgeSemantic(selectedJob.status)}
                        />
                      ) : null}
                      {jobDetailQuery.isLoading ? (
                        <Typography variant="caption" color="text.secondary">
                          Loading job…
                        </Typography>
                      ) : null}
                    </Box>
                    {jobDetailQuery.error ? (
                      <ErrorAlert
                        message={getApiErrorMessage(jobDetailQuery.error, 'Failed to load job details')}
                        onRetry={() => {
                          void jobDetailQuery.refetch();
                        }}
                      />
                    ) : null}
                    <Divider />
                    <Box sx={{ display: 'grid', gap: 0.75 }}>
                      {jobMetadataRows(selectedJob, executionEventsForFinished).map((item) => (
                        <Box
                          key={item.label}
                          sx={{ display: 'grid', gridTemplateColumns: 'minmax(100px, 120px) 1fr', gap: 0.5 }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            {item.label}
                          </Typography>
                          <Typography variant="caption" sx={{ wordBreak: 'break-word' }}>
                            {item.value}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </Stack>
                </Paper>
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Select a job to see live status and metadata.
                </Typography>
              )}
            </Box>

            <Box sx={{ flex: 1, minWidth: 0 }}>
              {logScope === 'job' && !selectedJobId ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                  Choose a job to load the job-scoped execution log from the API.
                </Typography>
              ) : (
                <ExecutionLogPanel
                  log={panelLog}
                  isLoading={panelLoading}
                  error={panelError}
                  emptyMessage={panelEmptyMessage}
                />
              )}
            </Box>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
