/**
 * Full-page (or embedded) aisle observability: execution logs, prompt inspection, attachments, traceability.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  Box,
  Button,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import type { ExecutionLogEvent, JobSummary } from '../api/types';
import { ApiError } from '../api/types';
import i18n from '../i18n';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { jobStatusToBadgeSemantic } from '../utils/jobStatus';
import { resolveDisplayFinishedAt } from '../utils/jobDisplayTimestamps';
import { deriveEffectiveJobDisplayState, shouldPollJobDetail } from '../utils/deriveJobDisplayState';
import { getJobProcessingStatusLabel } from '../utils/jobFinalizationLabels';
import AdminFinalizationRecoveryPanel from './AdminFinalizationRecoveryPanel';
import JobObservabilityDiagnosticsPanel from './JobObservabilityDiagnosticsPanel';
import { useAuth } from '../features/auth';
import { useExecutionLogDownloads } from '../features/executionLogs/hooks/useExecutionLogDownloads';
import ExecutionLogPanel from './ExecutionLogPanel';
import { ErrorAlert, StatusBadge, useAppSnackbar } from './ui';
import JobAuditabilityPanel from './JobAuditabilityPanel';
import {
  useAisleExecutionLog,
  useAisleJobDetail,
  useAisleJobsList,
  useCancelAisleJob,
  useExecutionLog,
  useRetryAisleJob,
} from '../hooks';
import {
  parseProviderRequestPayload,
  type GeminiAttachmentSlice,
  type ProviderRequestLogPayload,
} from '../utils/parseExecutionLogProviderRequest';
import { ProcessingWorkspace } from '../features/processing';
import { useProcessingObservabilityCapabilities } from '../features/processing/hooks';
import {
  PROCESSING_TAB_QUERY_VALUE,
  clearProcessingFilterParams,
} from '../features/processing/utils/processingUrlFilters';

const AISLE_OBSERVABILITY_JOBS_LIMIT = 500;

function formatOptionalDate(value?: string | null): string {
  return value ? formatDate(value) : i18n.t('common.em_dash');
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
  const dash = i18n.t('common.em_dash');
  return [
    { label: i18n.t('jobs.obs_started'), value: formatOptionalDate(job.started_at) },
    { label: i18n.t('jobs.obs_finished'), value: formatOptionalDate(displayFinished) },
    { label: i18n.t('jobs.obs_last_heartbeat'), value: formatOptionalDate(job.last_heartbeat_at) },
    { label: i18n.t('jobs.obs_cancel_requested'), value: formatOptionalDate(job.cancel_requested_at) },
    { label: i18n.t('jobs.obs_current_stage'), value: job.current_stage || dash },
    ...(job.execution_strategy
      ? [
          {
            label: i18n.t('jobs.obs_execution_strategy'),
            value: i18n.t(
              `aisle.execution_strategy_${String(job.execution_strategy).toLowerCase()}`,
              { defaultValue: String(job.execution_strategy) },
            ),
          },
          ...(job.identification_mode
            ? [
                {
                  label: i18n.t('jobs.obs_requested_mode', {
                    defaultValue: 'Requested mode',
                  }),
                  value: String(job.identification_mode),
                },
              ]
            : []),
          {
            label: i18n.t('jobs.obs_execution_scope'),
            value:
              String(job.execution_strategy) === 'CODE_SCAN' ||
              String(job.execution_strategy) === 'INTERNAL_OCR'
                ? i18n.t('aisle.execution_scope_single_asset')
                : i18n.t('aisle.execution_scope_aisle_batch'),
          },
        ]
      : []),
    ...(job.asset_progress
      ? [
          {
            label: i18n.t('jobs.obs_asset_progress'),
            value: i18n.t('jobs.obs_asset_progress_value_v2', {
              total: job.asset_progress.total,
              resolved: job.asset_progress.resolved,
              unrecognized: job.asset_progress.unrecognized,
              failed: job.asset_progress.failed,
              pending: job.asset_progress.pending,
              processing: job.asset_progress.processing,
              manual_review: job.asset_progress.manual_review,
              cancelled: job.asset_progress.cancelled,
            }),
          },
        ]
      : []),
    ...(job.fallback_progress
      ? [
          {
            label: i18n.t('jobs.obs_fallback_progress', {
              defaultValue: 'Fallback externo',
            }),
            value: i18n.t('jobs.obs_fallback_progress_value', {
              defaultValue:
                '{{resolved_internal}} internas · {{fallback_requested}} a fallback · {{resolved_external}} externas · {{external_failed}} fallidas · costo {{estimated_external_cost}}',
              resolved_internal: job.fallback_progress.resolved_internal,
              fallback_requested: job.fallback_progress.fallback_requested,
              resolved_external: job.fallback_progress.resolved_external,
              external_failed: job.fallback_progress.external_failed,
              estimated_external_cost:
                job.fallback_progress.estimated_external_cost == null
                  ? i18n.t('common.em_dash')
                  : String(job.fallback_progress.estimated_external_cost),
            }),
          },
        ]
      : []),
    ...(job.fallback_asset_summaries && job.fallback_asset_summaries.length > 0
      ? [
          {
            label: i18n.t('jobs.obs_fallback_assets', {
              defaultValue: 'Fallback por imagen',
            }),
            value: job.fallback_asset_summaries
              .slice(0, 8)
              .map((row) => {
                const parts = [
                  row.asset_id.slice(0, 8),
                  row.external_provider || '—',
                  row.external_model || '—',
                  row.fallback_status || '—',
                  row.persistence_status || '—',
                  row.internal_code || row.error_code || '—',
                ];
                return parts.join(' · ');
              })
              .join(' | '),
          },
        ]
      : []),
    { label: i18n.t('jobs.obs_current_step'), value: job.current_substep || dash },
    { label: i18n.t('jobs.obs_step_started'), value: formatOptionalDate(job.current_step_started_at) },
    { label: i18n.t('common.execution_id'), value: job.execution_id || dash },
    { label: i18n.t('jobs.obs_provider_row'), value: job.provider_name || dash },
    { label: i18n.t('jobs.obs_model_row'), value: job.model_name || dash },
    { label: i18n.t('jobs.obs_prompt_key'), value: job.prompt_key || dash },
    { label: i18n.t('jobs.obs_prompt_version'), value: job.prompt_version || dash },
    {
      label: i18n.t('jobs.obs_attempt_row'),
      value: job.attempt_count ? i18n.t('jobs.attempt_number', { count: job.attempt_count }) : dash,
    },
    { label: i18n.t('jobs.obs_retry_of_job'), value: job.retry_of_job_id || dash },
    { label: i18n.t('jobs.obs_failure_code'), value: job.failure_code || dash },
    {
      label: i18n.t('jobs.obs_failure_message'),
      value: job.failure_message || job.error_message || dash,
    },
  ];
}

function formatAttachmentLabel(item: GeminiAttachmentSlice): string {
  const id =
    item.reference_id ?? item.frame_ref ?? item.role ?? i18n.t('execution_log.attachment_id_fallback');
  const filename = item.filename ?? i18n.t('execution_log.unknown_file');
  const mime = item.mime_type ? ` (${item.mime_type})` : '';
  const resolved =
    item.role === 'visual_reference' && item.resolved === false
      ? i18n.t('execution_log.not_resolved_suffix')
      : '';
  return `${id}: ${filename}${mime}${resolved}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export interface AisleObservabilityWorkspaceProps {
  inventoryId: string;
  aisleId: string;
  aisleCode: string;
  initialSelectedJobId: string | null;
  /** When false, observability queries stay disabled (e.g. unmounted page). */
  active: boolean;
  onAislesInvalidate?: () => Promise<unknown>;
}

type LogScope = 'merged' | 'job';

type ObsContentTab =
  | 'events'
  | 'processing'
  | 'prompt'
  | 'attachments'
  | 'traceability'
  | 'auditability'
  | 'diagnostics';

function buildObsContentTabs(processingEnabled: boolean): ObsContentTab[] {
  const base: ObsContentTab[] = [
    'events',
    'prompt',
    'attachments',
    'traceability',
    'auditability',
    'diagnostics',
  ];
  if (!processingEnabled) return base;
  return ['events', 'processing', ...base.slice(1)];
}

export default function AisleObservabilityWorkspace({
  inventoryId,
  aisleId,
  aisleCode,
  initialSelectedJobId,
  active,
  onAislesInvalidate,
}: AisleObservabilityWorkspaceProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [searchParams, setSearchParams] = useSearchParams();
  const processingCapabilities = useProcessingObservabilityCapabilities({ enabled: active });
  const processingObservabilityEnabled = processingCapabilities.processing_observability_enabled;
  const contentTabs = useMemo(
    () => buildObsContentTabs(processingObservabilityEnabled),
    [processingObservabilityEnabled]
  );
  const [logScope, setLogScope] = useState<LogScope>(() => (initialSelectedJobId ? 'job' : 'merged'));
  const [selectedJobId, setSelectedJobId] = useState<string>(() => initialSelectedJobId ?? '');
  const [contentTab, setContentTab] = useState<ObsContentTab>(() =>
    searchParams.get('tab') === PROCESSING_TAB_QUERY_VALUE && processingObservabilityEnabled
      ? 'processing'
      : 'events'
  );

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab === PROCESSING_TAB_QUERY_VALUE && processingObservabilityEnabled) {
      setContentTab('processing');
      return;
    }
    setContentTab((current) => (current === 'processing' ? 'events' : current));
  }, [searchParams, processingObservabilityEnabled]);

  useEffect(() => {
    if (initialSelectedJobId) {
      setSelectedJobId(initialSelectedJobId);
      setLogScope('job');
    }
  }, [initialSelectedJobId]);

  const aisleExecutionLogQuery = useAisleExecutionLog(inventoryId, aisleId, {
    enabled: active && Boolean(inventoryId && aisleId),
  });
  const jobsListQuery = useAisleJobsList(inventoryId, aisleId, {
    enabled: active && Boolean(inventoryId && aisleId),
    limit: AISLE_OBSERVABILITY_JOBS_LIMIT,
  });
  const { user } = useAuth();
  const pollStartedAtRef = useRef<number>(Date.now());
  useEffect(() => {
    pollStartedAtRef.current = Date.now();
  }, [selectedJobId]);

  const jobDetailQuery = useAisleJobDetail(inventoryId, aisleId, selectedJobId || undefined, {
    enabled: active && Boolean(inventoryId && aisleId && selectedJobId),
    refetchInterval: (query) => {
      const job = query.state.data;
      const elapsed = Date.now() - pollStartedAtRef.current;
      return shouldPollJobDetail(job ?? null, elapsed) ? 4000 : false;
    },
  });
  const executionLogQuery = useExecutionLog(inventoryId, aisleId, selectedJobId || undefined, {
    enabled: active && Boolean(inventoryId && aisleId && selectedJobId) && logScope === 'job',
  });

  const cancelJobMutation = useCancelAisleJob(inventoryId);
  const retryJobMutation = useRetryAisleJob(inventoryId);
  const {
    downloadMergedExecutionLog,
    downloadJobExecutionLog,
    isDownloadingMerged,
    isDownloadingJobLog,
    clearError: clearDownloadError,
  } = useExecutionLogDownloads({
    inventoryId,
    aisleId,
  });

  const selectedJob = jobDetailQuery.data ?? null;
  const jobs = jobsListQuery.data?.jobs ?? [];

  const executionEventsForFinished = logScope === 'job' ? executionLogQuery.data?.events : null;

  const panelLog = logScope === 'merged' ? aisleExecutionLogQuery.data ?? null : executionLogQuery.data ?? null;
  const panelLoading = logScope === 'merged' ? aisleExecutionLogQuery.isLoading : executionLogQuery.isLoading;
  const panelError = logScope === 'merged' ? aisleExecutionLogQuery.error : executionLogQuery.error;
  const panelEmptyMessage =
    logScope === 'merged'
      ? t('jobs.obs_empty_aisle')
      : selectedJobId
        ? t('jobs.obs_empty_job')
        : t('jobs.obs_select_job');

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
      showSnackbar(t('jobs.cancel_success'), 'success');
      await handleRefresh();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.cancel_job'), 'error');
    }
  };

  const handleRetryJob = async () => {
    if (!selectedJobId) return;
    try {
      const result = await retryJobMutation.mutateAsync({ aisleId, jobId: selectedJobId });
      setSelectedJobId(result.id);
      setLogScope('job');
      showSnackbar(
        t('jobs.retry_started', { attempt: result.attempt_count ?? 'new' }),
        'success',
      );
      await Promise.all([
        onAislesInvalidate?.(),
        aisleExecutionLogQuery.refetch(),
        jobsListQuery.refetch(),
      ]);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.retry_job'), 'error');
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
  };

  const onContentTabChange = (_: unknown, nextIndex: number) => {
    const nextTab = contentTabs[nextIndex] ?? 'events';
    setContentTab(nextTab);
    const nextParams =
      nextTab === 'processing'
        ? (() => {
            const params = new URLSearchParams(searchParams);
            params.set('tab', PROCESSING_TAB_QUERY_VALUE);
            return params;
          })()
        : clearProcessingFilterParams(searchParams);
    setSearchParams(nextParams, { replace: true });
  };

  const contentTabIndex = Math.max(0, contentTabs.indexOf(contentTab));

  const lastProviderRequest = useMemo((): {
    event: ExecutionLogEvent;
    request: ProviderRequestLogPayload;
  } | null => {
    const events = panelLog?.events ?? [];
    let last: { event: ExecutionLogEvent; request: ProviderRequestLogPayload } | null = null;
    for (const e of events) {
      const p = parseProviderRequestPayload(e);
      if (p) last = { event: e, request: p };
    }
    return last;
  }, [panelLog]);

  const effectivePrompt = useMemo(() => {
    const comp = lastProviderRequest?.request.prompt_composition;
    if (!comp) return null;
    const eff = comp.effective_prompt;
    return asRecord(eff);
  }, [lastProviderRequest]);

  const copyPrompt = async () => {
    const text = lastProviderRequest?.request.prompt_text;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showSnackbar(t('jobs.obs_prompt_copied'), 'success');
    } catch {
      showSnackbar(t('jobs.obs_prompt_copy_failed'), 'error');
    }
  };

  const downloadPromptTxt = () => {
    const text = lastProviderRequest?.request.prompt_text;
    if (!text) return;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `prompt-${aisleCode}-${selectedJobId || 'merged'}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const translateResolutionStatus = (raw: string | undefined): string => {
    const k = String(raw ?? '').toLowerCase();
    if (k === 'resolved') return t('jobs.trace_status_resolved');
    if (k === 'fallback') return t('jobs.trace_status_fallback');
    if (k === 'error') return t('jobs.trace_status_error');
    return raw ?? t('common.em_dash');
  };

  const translateFallbackReason = (raw: string | undefined): string => {
    const k = String(raw ?? '').trim();
    if (!k) return t('common.em_dash');
    const map: Record<string, string> = {
      INVENTORY_WITHOUT_CLIENT: t('jobs.trace_fb_inventory_without_client'),
      AISLE_WITHOUT_CLIENT_SUPPLIER: t('jobs.trace_fb_aisle_without_supplier'),
      NO_ACTIVE_SUPPLIER_PROMPT_CONFIG: t('jobs.trace_fb_no_active_supplier_prompt_config'),
      fallback_inventory_without_client: t('jobs.trace_fb_inventory_without_client'),
      fallback_aisle_without_client_supplier: t('jobs.trace_fb_aisle_without_supplier'),
      fallback_no_active_reference_images: t('jobs.trace_fb_no_active_reference_images'),
    };
    return map[k] ?? t('jobs.trace_fb_other', { code: k });
  };

  const translateResolutionErrorCode = (raw: string | undefined): string => {
    const k = String(raw ?? '').trim();
    if (!k) return t('common.em_dash');
    const map: Record<string, string> = {
      NO_ACTIVE_SUPPLIER_PROMPT_CONFIG: t('jobs.trace_err_no_active_supplier_prompt_config'),
    };
    return map[k] ?? t('jobs.trace_err_resolution_other', { code: k });
  };

  const referenceSourceDisplay = (raw: string) => {
    if (raw === 'supplier_reference_images') return t('jobs.trace_ref_src_supplier_refs');
    return raw;
  };

  const promptComposition = lastProviderRequest?.request.prompt_composition ?? null;

  return (
    <Stack spacing={2} data-testid="aisle-observability-workspace">
      <Typography variant="h6" component="h1">
        {t('jobs.dialog_title_aisle', { code: aisleCode })}
      </Typography>

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
          {refreshBusy ? t('common.refreshing') : t('jobs.refresh')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          disabled={!inventoryId || isDownloadingMerged}
          onClick={async () => {
            clearDownloadError();
            try {
              await downloadMergedExecutionLog();
            } catch (e) {
              const err = e instanceof ApiError ? e : new ApiError(String(e));
              showSnackbar(resolveApiErrorMessage(err, 'errors.download_merged_log'), 'error');
            }
          }}
        >
          {isDownloadingMerged ? t('jobs.downloading') : t('common.download_merged_log')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          disabled={!inventoryId || !selectedJobId || isDownloadingJobLog}
          onClick={async () => {
            if (!selectedJobId) return;
            clearDownloadError();
            try {
              await downloadJobExecutionLog(selectedJobId);
            } catch (e) {
              const err = e instanceof ApiError ? e : new ApiError(String(e));
              showSnackbar(resolveApiErrorMessage(err, 'errors.download_job_log'), 'error');
            }
          }}
        >
          {isDownloadingJobLog ? t('jobs.downloading') : t('common.download_selected_job_log')}
        </Button>
        {selectedJobId ? (
          <>
            {isCancelRequested(selectedJob?.status) ? (
              <Button size="small" variant="outlined" disabled>
                {t('jobs.obs_cancel_requested')}
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
                {cancelJobMutation.isPending ? t('common.cancelling') : t('jobs.cancel_job')}
              </Button>
            ) : null}
            {canRetryJob(selectedJob?.status) ? (
              <Button
                size="small"
                variant="contained"
                onClick={() => void handleRetryJob()}
                disabled={retryJobMutation.isPending}
              >
                {retryJobMutation.isPending ? t('common.retrying') : t('jobs.retry_job')}
              </Button>
            ) : null}
          </>
        ) : null}
      </Box>

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', lg: 'row' },
          gap: 2,
          alignItems: 'stretch',
        }}
      >
        <Box
          sx={{
            flex: { lg: '0 0 300px' },
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5,
          }}
        >
          <FormControl size="small" fullWidth>
            <InputLabel id="obs-scope-label">{t('jobs.log_scope')}</InputLabel>
            <Select
              labelId="obs-scope-label"
              label={t('jobs.log_scope')}
              value={logScope}
              onChange={(e) => onScopeChange(e.target.value as LogScope)}
            >
              <MenuItem value="merged">{t('jobs.scope_merged')}</MenuItem>
              <MenuItem value="job">{t('jobs.scope_selected_job')}</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" fullWidth>
            <InputLabel id="obs-job-label">{t('common.job')}</InputLabel>
            <Select
              labelId="obs-job-label"
              label={t('common.job')}
              value={selectedJobId}
              onChange={(e) => onJobSelectChange(e.target.value)}
              disabled={jobsListQuery.isLoading}
            >
              <MenuItem value="">
                <em>{t('jobs.obs_none_merged_only')}</em>
              </MenuItem>
              {jobs.map((j) => (
                <MenuItem key={j.id} value={j.id}>
                  {jobOptionLabel(j)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {selectedJobId ? (
            <Paper variant="outlined" sx={{ p: 1.25, maxHeight: 280, overflow: 'auto' }}>
              <Stack spacing={1}>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, alignItems: 'center' }}>
                  {selectedJob ? (
                    <StatusBadge
                      label={getJobProcessingStatusLabel(selectedJob, t)}
                      semantic={
                        (() => {
                          const display = deriveEffectiveJobDisplayState(selectedJob);
                          if (display === 'failed') return 'error';
                          if (display === 'completed') return 'success';
                          if (display === 'completed_with_finalization_warning') return 'warning';
                          if (display === 'canceled') return 'warning';
                          return jobStatusToBadgeSemantic(selectedJob.status);
                        })()
                      }
                    />
                  ) : null}
                  {jobDetailQuery.isLoading ? (
                    <Typography variant="caption" color="text.secondary">
                      {t('jobs.obs_loading_job_detail')}
                    </Typography>
                  ) : null}
                </Box>
                {jobDetailQuery.error ? (
                  <ErrorAlert
                    message={resolveApiErrorMessage(jobDetailQuery.error, 'errors.load_job_details')}
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
                <AdminFinalizationRecoveryPanel
                  job={selectedJob}
                  isAdmin={user?.role === 'administrator'}
                  onRecovered={handleRefresh}
                />
              </Stack>
            </Paper>
          ) : (
            <Typography variant="caption" color="text.secondary">
              {t('jobs.obs_select_job_metadata_hint')}
            </Typography>
          )}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Tabs
            value={contentTabIndex}
            onChange={onContentTabChange}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
          >
            <Tab label={t('jobs.obs_tab_events')} />
            {processingObservabilityEnabled ? (
              <Tab label={t('jobs.obs_tab_processing')} data-testid="obs-tab-processing" />
            ) : null}
            <Tab label={t('jobs.obs_tab_prompt')} />
            <Tab label={t('jobs.obs_tab_attachments')} />
            <Tab label={t('jobs.obs_tab_traceability')} />
            <Tab label={t('jobs.obs_tab_auditability')} />
            <Tab label={t('jobs.obs_tab_diagnostics')} />
          </Tabs>

          {contentTab === 'events' ? (
            logScope === 'job' && !selectedJobId ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                {t('jobs.obs_choose_job_for_log')}
              </Typography>
            ) : (
              <ExecutionLogPanel
                log={panelLog}
                isLoading={panelLoading}
                error={panelError}
                emptyMessage={panelEmptyMessage}
                prettyPrintPayload
              />
            )
          ) : null}

          {contentTab === 'processing' ? (
            logScope === 'job' && selectedJobId ? (
              <ProcessingWorkspace
                inventoryId={inventoryId}
                aisleId={aisleId}
                jobId={selectedJobId}
                selectedJob={selectedJob}
                active={active}
              />
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                {t('jobs.obs_choose_job_for_log')}
              </Typography>
            )
          ) : null}

          {contentTab === 'prompt' ? (
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary">
                {t('jobs.obs_prompt_audit_notice')}
              </Typography>
              {!lastProviderRequest ? (
                <Typography variant="body2" color="text.secondary">
                  {t('jobs.obs_prompt_no_request_event')}
                </Typography>
              ) : (
                <>
                  <Paper variant="outlined" sx={{ p: 2, display: 'grid', gap: 1 }}>
                    <Typography variant="subtitle2">{t('jobs.obs_prompt_meta_heading')}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_prompt_profile_row', {
                        profile:
                          (typeof promptComposition?.profile_name === 'string' &&
                            promptComposition.profile_name.trim()) ||
                          t('common.em_dash'),
                      })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_prompt_provider_pipeline', {
                        pipeline: lastProviderRequest.request.pipeline_provider ?? t('common.em_dash'),
                      })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_prompt_model_row', {
                        model:
                          (typeof promptComposition?.model_name === 'string' && promptComposition.model_name) ||
                          selectedJob?.model_name ||
                          t('common.em_dash'),
                      })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_prompt_hash_row', {
                        hash:
                          (typeof promptComposition?.prompt_hash === 'string' && promptComposition.prompt_hash) ||
                          lastProviderRequest.request.prompt_text_sha256 ||
                          t('common.em_dash'),
                      })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_prompt_len_row', {
                        len:
                          (typeof promptComposition?.final_prompt_char_len === 'number' &&
                            promptComposition.final_prompt_char_len) ??
                          lastProviderRequest.request.prompt_text_len ??
                          t('common.em_dash'),
                      })}
                    </Typography>
                    {typeof promptComposition?.job_prompt_key === 'string' &&
                    promptComposition.job_prompt_key.trim() ? (
                      <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                        {t('jobs.obs_prompt_job_key_row', { key: promptComposition.job_prompt_key.trim() })}
                      </Typography>
                    ) : null}
                    {typeof promptComposition?.settings_hybrid_prompt_key === 'string' &&
                    promptComposition.settings_hybrid_prompt_key.trim() ? (
                      <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                        {t('jobs.obs_prompt_settings_key_row', {
                          key: promptComposition.settings_hybrid_prompt_key.trim(),
                        })}
                      </Typography>
                    ) : null}
                  </Paper>
                  {lastProviderRequest.request.prompt_text ? (
                    <>
                      <Typography variant="subtitle2">{t('jobs.obs_prompt_complete_heading')}</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                        <Button size="small" variant="outlined" onClick={() => void copyPrompt()}>
                          {t('jobs.obs_copy_prompt')}
                        </Button>
                        <Button size="small" variant="outlined" onClick={downloadPromptTxt}>
                          {t('jobs.obs_download_prompt')}
                        </Button>
                      </Box>
                      <Box
                        component="pre"
                        sx={{
                          m: 0,
                          p: 2,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                          maxHeight: 480,
                          overflow: 'auto',
                          borderRadius: 1,
                          bgcolor: 'action.hover',
                          border: 1,
                          borderColor: 'divider',
                        }}
                      >
                        {lastProviderRequest.request.prompt_text}
                      </Box>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.obs_full_prompt_unavailable_actionable')}
                    </Typography>
                  )}
                </>
              )}
            </Stack>
          ) : null}

          {contentTab === 'attachments' ? (
            lastProviderRequest ? (
              <Stack spacing={2}>
                <Typography variant="subtitle2">{t('execution_log.attached_files')}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('execution_log.attachment_counts', {
                    primary: lastProviderRequest.request.attachment_summary?.primary_evidence_count ?? 0,
                    refs: lastProviderRequest.request.attachment_summary?.visual_reference_count ?? 0,
                    total: lastProviderRequest.request.attachment_summary?.total_count ?? 0,
                  })}
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {t('execution_log.primary_evidence')}
                </Typography>
                {lastProviderRequest.request.primary_evidence_attachments?.length ? (
                  <Stack spacing={0.5}>
                    {lastProviderRequest.request.primary_evidence_attachments.map((item, index) => (
                      <Typography key={`p-${index}`} variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {formatAttachmentLabel(item)}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('execution_log.no_primary_evidence')}
                  </Typography>
                )}
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {t('execution_log.reference_images')}
                </Typography>
                {lastProviderRequest.request.visual_reference_attachments?.length ? (
                  <Stack spacing={0.5}>
                    {lastProviderRequest.request.visual_reference_attachments.map((item, index) => (
                      <Typography key={`r-${index}`} variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {formatAttachmentLabel(item)}
                      </Typography>
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t('execution_log.no_reference_images')}
                  </Typography>
                )}
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t('jobs.obs_attachments_no_request')}
              </Typography>
            )
          ) : null}

          {contentTab === 'traceability' ? (
            <Stack spacing={2}>
              {!effectivePrompt && !promptComposition ? (
                <Typography variant="body2" color="text.secondary">
                  {t('jobs.obs_trace_no_composition')}
                </Typography>
              ) : (
                <>
                  <Typography variant="subtitle2">{t('jobs.trace_supplier_prompt_heading')}</Typography>
                  {effectivePrompt ? (
                    <Paper variant="outlined" sx={{ p: 2, display: 'grid', gap: 1 }}>
                      <Typography variant="body2">
                        <strong>{t('jobs.trace_resolution_status')}</strong>{' '}
                        {translateResolutionStatus(
                          typeof effectivePrompt.resolution_status === 'string'
                            ? effectivePrompt.resolution_status
                            : undefined
                        )}
                      </Typography>
                      {String(effectivePrompt.resolution_status ?? '').toLowerCase() === 'error' &&
                      typeof effectivePrompt.resolution_error_code === 'string' &&
                      effectivePrompt.resolution_error_code.trim() ? (
                        <Typography variant="body2" color="error">
                          <strong>{t('jobs.trace_resolution_error_detail')}</strong>{' '}
                          {translateResolutionErrorCode(effectivePrompt.resolution_error_code)}
                        </Typography>
                      ) : null}
                      <Typography variant="body2">
                        <strong>{t('jobs.trace_supplier_instructions_applied')}</strong>{' '}
                        {typeof effectivePrompt.supplier_instructions_applied === 'boolean'
                          ? effectivePrompt.supplier_instructions_applied
                            ? t('common.yes')
                            : t('common.no')
                          : t('common.em_dash')}
                      </Typography>
                      <Typography variant="body2">
                        <strong>{t('jobs.trace_config_id')}</strong>{' '}
                        {String(effectivePrompt.supplier_prompt_config_id ?? t('common.em_dash'))}
                      </Typography>
                      <Typography variant="body2">
                        <strong>{t('jobs.trace_config_version')}</strong>{' '}
                        {String(effectivePrompt.supplier_prompt_config_version ?? t('common.em_dash'))}
                      </Typography>
                      {effectivePrompt.fallback_used === true ? (
                        <Typography variant="body2" color="warning.main">
                          <strong>{t('jobs.trace_fallback_reason')}</strong>{' '}
                          {translateFallbackReason(
                            typeof effectivePrompt.fallback_reason === 'string'
                              ? effectivePrompt.fallback_reason
                              : undefined
                          )}
                        </Typography>
                      ) : null}
                    </Paper>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      {t('jobs.trace_no_effective_prompt')}
                    </Typography>
                  )}

                  <Typography variant="subtitle2">{t('jobs.trace_reference_images_heading')}</Typography>
                  <Paper variant="outlined" sx={{ p: 2, display: 'grid', gap: 1 }}>
                    <Typography variant="body2">
                      <strong>{t('jobs.trace_reference_source')}</strong>{' '}
                      {typeof effectivePrompt?.reference_source === 'string'
                        ? referenceSourceDisplay(String(effectivePrompt.reference_source))
                        : t('common.em_dash')}
                    </Typography>
                    <Typography variant="body2">
                      <strong>{t('jobs.trace_reference_count_used')}</strong>{' '}
                      {Array.isArray(effectivePrompt?.reference_image_ids)
                        ? effectivePrompt.reference_image_ids.length
                        : 0}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                      {t('jobs.trace_hybrid_report_note')}
                    </Typography>
                  </Paper>
                </>
              )}
            </Stack>
          ) : null}

          {contentTab === 'auditability' ? (
            logScope === 'job' && selectedJobId ? (
              <JobAuditabilityPanel
                inventoryId={inventoryId}
                aisleId={aisleId}
                jobId={selectedJobId}
                active={active}
              />
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                {t('jobs.obs_choose_job_for_log')}
              </Typography>
            )
          ) : null}

          {contentTab === 'diagnostics' ? (
            selectedJobId ? (
              <JobObservabilityDiagnosticsPanel
                inventoryId={inventoryId}
                aisleId={aisleId}
                jobId={selectedJobId}
                active={active}
                onSelectAttempt={(id) => {
                  setSelectedJobId(id);
                  setLogScope('job');
                }}
              />
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                {t('jobs.obs_choose_job_for_log')}
              </Typography>
            )
          ) : null}
        </Box>
      </Box>
    </Stack>
  );
}
