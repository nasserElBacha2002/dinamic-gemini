import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../utils/jobStatus';
import { getAisleStatusLabel, aisleStatusToBadgeSemantic } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import { resolveDisplayFinishedAt } from '../utils/jobDisplayTimestamps';
import type { ExecutionLogEvent } from '../api/types';
import { exportInventoryResultsCsv } from '../api/client';
import {
  DataTable,
  ErrorAlert,
  LoadingBlock,
  RowActionMenu,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateAisleDialog from '../components/CreateAisleDialog';
import ExecutionLogPanel from '../components/ExecutionLogPanel';
import ReferenceImagesDrawer from '../components/ReferenceImagesDrawer';
import {
  useInventoryDetail,
  useInventoryVisualReferences,
  useAislesList,
  useProcessingProviderOptions,
  useExecutionLog,
  useAisleJobDetail,
  useCreateAisle,
  useStartAisleProcessing,
  useCancelAisleJob,
  useRetryAisleJob,
  useUploadAisleAssetsFlex,
  useUploadInventoryVisualReferences,
  useDeleteInventoryVisualReference,
  useReplaceInventoryVisualReference,
} from '../hooks';

function getUploadContextFromInput(
  e: React.ChangeEvent<HTMLInputElement>,
  pendingAisleIdRef: React.MutableRefObject<string | null>
): { files: File[]; aisleId: string } | null {
  const aisleId = pendingAisleIdRef.current;
  const files = e.target.files;
  if (!aisleId || !files?.length) return null;
  return { files: Array.from(files), aisleId };
}

function formatReferenceUsageSummary(aisle: Aisle): { label: string; detail?: string; semantic: 'success' | 'warning' | 'error' | 'neutral' } | null {
  const usage = aisle.latest_job?.reference_usage;
  if (!aisle.latest_job) return null;
  if (!usage) {
    return ['queued', 'running'].includes(String(aisle.latest_job.status).toLowerCase())
      ? { label: 'Pending run summary', semantic: 'neutral' }
      : { label: 'Summary unavailable', semantic: 'neutral' };
  }

  const preparedLabel = usage.resolved_count === 1 ? '1 prepared' : `${usage.resolved_count} prepared`;
  const sentLabel = usage.provider_consumed_count === 1 ? '1 sent to Gemini' : `${usage.provider_consumed_count} sent to Gemini`;

  if (usage.resolution_error) {
    return {
      label: 'Reference setup failed',
      detail: `${preparedLabel}. Not sent to Gemini.`,
      semantic: 'error',
    };
  }

  if (usage.provider_consumed) {
    return {
      label: sentLabel,
      detail: preparedLabel,
      semantic: 'success',
    };
  }

  if (usage.resolved) {
    return {
      label: 'References not sent',
      detail: preparedLabel,
      semantic: 'warning',
    };
  }

  return {
    label: 'Processed without references',
    semantic: 'neutral',
  };
}

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

/** Shown when Process aisle is disabled due to no uploaded source assets (`assets_count` on the aisle row). */
const PROCESS_AISLE_NEEDS_ASSETS_MESSAGE =
  'You need to upload at least one image before processing.';

function metadataRowsForJob(
  job: NonNullable<Aisle['latest_job']> | null | undefined,
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
    { label: 'Attempt', value: job.attempt_count ? `Attempt ${job.attempt_count}` : '—' },
    { label: 'Retry of job', value: job.retry_of_job_id || '—' },
    { label: 'Failure code', value: job.failure_code || '—' },
    { label: 'Failure message', value: job.failure_message || job.error_message || '—' },
  ];
}

export default function InventoryDetail() {
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [jobDialog, setJobDialog] = useState<{ aisleId: string; jobId: string; aisleCode: string } | null>(null);
  const [processDialog, setProcessDialog] = useState<{ aisleId: string; aisleCode: string } | null>(null);
  const [processProviderKey, setProcessProviderKey] = useState('');
  const [processModelKey, setProcessModelKey] = useState('');
  const [processPromptKey, setProcessPromptKey] = useState('');
  const [referenceImagesOpen, setReferenceImagesOpen] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadAisleIdRef = useRef<string | null>(null);

  const executionLogQuery = useExecutionLog(
    inventoryId ?? undefined,
    jobDialog?.aisleId,
    jobDialog?.jobId,
    {
      enabled: Boolean(jobDialog),
    }
  );
  const jobDetailQuery = useAisleJobDetail(
    inventoryId ?? undefined,
    jobDialog?.aisleId,
    jobDialog?.jobId,
    {
      enabled: Boolean(jobDialog),
    }
  );

  const inventoryQuery = useInventoryDetail(inventoryId);
  const visualReferencesQuery = useInventoryVisualReferences(inventoryId, {
    enabled: Boolean(referenceImagesOpen && inventoryId && inventoryQuery.data),
  });
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });
  const aisles = aislesQuery.data?.items ?? [];
  const processingProviderOptsQuery = useProcessingProviderOptions({
    enabled: Boolean(processDialog && inventoryId),
  });

  const effectiveProcessProvider =
    processProviderKey.trim() || processingProviderOptsQuery.data?.default_provider_key || '';
  const providerConfigForProcess = useMemo(
    () =>
      (processingProviderOptsQuery.data?.providers ?? []).find((p) => p.key === effectiveProcessProvider),
    [processingProviderOptsQuery.data?.providers, effectiveProcessProvider]
  );

  useEffect(() => {
    setProcessModelKey('');
  }, [processProviderKey]);

  const createAisleMutation = useCreateAisle(inventoryId ?? '');
  const processMutation = useStartAisleProcessing(inventoryId ?? '');
  const cancelJobMutation = useCancelAisleJob(inventoryId ?? '');
  const retryJobMutation = useRetryAisleJob(inventoryId ?? '');
  const uploadMutation = useUploadAisleAssetsFlex(inventoryId ?? '');
  const uploadReferenceImagesMutation = useUploadInventoryVisualReferences(inventoryId ?? '');
  const deleteReferenceImageMutation = useDeleteInventoryVisualReference(inventoryId ?? '');
  const replaceReferenceImageMutation = useReplaceInventoryVisualReference(inventoryId ?? '');

  const inventory = inventoryQuery.data ?? null;
  const selectedJob = jobDetailQuery.data ?? null;
  const inventoryLoading = inventoryQuery.isLoading;
  const inventoryError =
    inventoryQuery.isError && inventoryQuery.error
      ? inventoryQuery.error instanceof ApiError && inventoryQuery.error.status === 404
        ? 'Inventory not found'
        : getApiErrorMessage(inventoryQuery.error, 'Failed to load inventory')
      : null;
  const aislesLoading = aislesQuery.isLoading;
  const aislesError =
    aislesQuery.isError && aislesQuery.error
      ? getApiErrorMessage(aislesQuery.error, 'Failed to load aisles')
      : null;
  const visualReferences = visualReferencesQuery.data?.items ?? [];
  const visualReferencesError =
    visualReferencesQuery.isError && visualReferencesQuery.error
      ? getApiErrorMessage(visualReferencesQuery.error, 'Failed to load reference images')
      : null;

  const handleCreateAisleSuccess = () => {
    showSnackbar('Aisle created', 'success');
    void aislesQuery.refetch();
  };

  const handleCloseReferenceImages = () => {
    setReferenceImagesOpen(false);
    uploadReferenceImagesMutation.reset();
    deleteReferenceImageMutation.reset();
    replaceReferenceImageMutation.reset();
  };

  const openProcessDialogForAisle = useCallback((aisleId: string, aisleCode: string) => {
    setProcessError(null);
    setProcessProviderKey('');
    setProcessModelKey('');
    setProcessPromptKey('');
    setProcessDialog({ aisleId, aisleCode });
  }, []);

  const closeProcessDialog = useCallback(() => {
    setProcessDialog(null);
  }, []);

  const confirmProcessDialog = useCallback(async () => {
    if (!processDialog) return;
    setProcessError(null);
    setUploadError(null);
    setProcessingAisleId(processDialog.aisleId);
    try {
      await processMutation.mutateAsync({
        aisleId: processDialog.aisleId,
        providerName: processProviderKey.trim() === '' ? null : processProviderKey.trim().toLowerCase(),
        modelName: processModelKey.trim() === '' ? null : processModelKey.trim(),
        promptKey: processPromptKey.trim() === '' ? null : processPromptKey.trim(),
      });
      showSnackbar('Processing started', 'success');
      setProcessDialog(null);
      void aislesQuery.refetch();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(getApiErrorMessage(err, 'Failed to start processing'));
    } finally {
      setProcessingAisleId(null);
    }
  }, [aislesQuery, processDialog, processModelKey, processMutation, processPromptKey, processProviderKey, showSnackbar]);

  const isAisleProcessingDisabled = useCallback(
    (aisle: Aisle): boolean => {
      const status = (aisle.status || '').toLowerCase();
      return status === 'queued' || status === 'processing' || processingAisleId === aisle.id;
    },
    [processingAisleId]
  );

  /** Uses `assets_count` from the aisles list (same source as the Uploaded assets column). */
  const getProcessAisleMenuState = useCallback(
    (aisle: Aisle): { disabled: boolean; disabledReason?: string } => {
      const busy = isAisleProcessingDisabled(aisle);
      const noListYet = !aislesQuery.data;
      const missingAssets = Boolean(aislesQuery.data) && (aisle.assets_count ?? 0) < 1;
      const disabled = busy || noListYet || missingAssets;
      if (busy) {
        return { disabled };
      }
      if (noListYet) {
        return {
          disabled,
          disabledReason: aislesQuery.isLoading
            ? 'Loading aisle data…'
            : 'Unable to verify uploaded assets.',
        };
      }
      if (missingAssets) {
        return { disabled, disabledReason: PROCESS_AISLE_NEEDS_ASSETS_MESSAGE };
      }
      return { disabled };
    },
    [aislesQuery.data, aislesQuery.isLoading, isAisleProcessingDisabled]
  );

  const handleUploadClick = (aisleId: string) => {
    setUploadError(null);
    pendingUploadAisleIdRef.current = aisleId;
    fileInputRef.current?.click();
  };

  const refreshJobOperations = async () => {
    await Promise.all([
      aislesQuery.refetch(),
      jobDetailQuery.refetch(),
      executionLogQuery.refetch(),
    ]);
  };

  const handleCancelJob = async () => {
    if (!jobDialog) return;
    try {
      await cancelJobMutation.mutateAsync({ aisleId: jobDialog.aisleId, jobId: jobDialog.jobId });
      showSnackbar('Cancellation requested', 'success');
      await refreshJobOperations();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(getApiErrorMessage(err, 'Failed to cancel job'), 'error');
    }
  };

  const handleRetryJob = async () => {
    if (!jobDialog) return;
    try {
      const result = await retryJobMutation.mutateAsync({ aisleId: jobDialog.aisleId, jobId: jobDialog.jobId });
      setJobDialog((current) =>
        current ? { ...current, jobId: result.id } : current
      );
      showSnackbar(`Retry started as attempt ${result.attempt_count ?? 'new'}`, 'success');
      await Promise.all([aislesQuery.refetch(), executionLogQuery.refetch(), jobDetailQuery.refetch()]);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(getApiErrorMessage(err, 'Failed to retry job'), 'error');
    }
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const ctx = getUploadContextFromInput(e, pendingUploadAisleIdRef);
    pendingUploadAisleIdRef.current = null;
    e.target.value = '';
    if (!inventoryId || !ctx) return;

    setUploadError(null);
    setProcessError(null);
    setUploadingAisleId(ctx.aisleId);
    try {
      const result = await uploadMutation.mutateAsync({ aisleId: ctx.aisleId, files: ctx.files });
      showSnackbar(`${result.assets.length} asset(s) uploaded`, 'success');
      void aislesQuery.refetch();
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
      setUploadError(getApiErrorMessage(apiErr, 'Upload failed'));
    } finally {
      setUploadingAisleId(null);
    }
  };

  const aisleColumns = useMemo<DataTableColumn<Aisle>[]>(() => {
    return [
      {
        id: 'code',
        label: 'Aisle code',
        cell: (a) => (
          <Button
            variant="text"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              navigate(pathToAislePositions(inventoryId ?? '', a.id));
            }}
            sx={{
              fontWeight: 650,
              textTransform: 'none',
              px: 0,
              minWidth: 0,
              justifyContent: 'flex-start',
              '&:hover': { textDecoration: 'underline', backgroundColor: 'transparent' },
            }}
          >
            {a.code}
          </Button>
        ),
      },
      {
        id: 'aisle_status',
        label: 'Aisle status',
        cell: (a) => (
          <StatusBadge
            label={getAisleStatusLabel(String(a.status))}
            semantic={aisleStatusToBadgeSemantic(String(a.status))}
          />
        ),
      },
      {
        id: 'assets',
        label: 'Uploaded assets',
        align: 'right',
        cell: (a) => (typeof a.assets_count === 'number' ? a.assets_count : '—'),
      },
      {
        id: 'processing',
        label: 'Processing status',
        cell: (a) =>
          a.latest_job ? (
            <StatusBadge
              label={getJobStatusLabel(a.latest_job.status)}
              semantic={jobStatusToBadgeSemantic(a.latest_job.status)}
            />
          ) : (
            '—'
          ),
      },
      {
        id: 'run_provider',
        label: 'Run provider',
        cell: (a) => (a.latest_job?.provider_name ? String(a.latest_job.provider_name) : '—'),
      },
      {
        id: 'run_model',
        label: 'Run model',
        cell: (a) => (a.latest_job?.model_name ? String(a.latest_job.model_name) : '—'),
      },
      {
        id: 'reference_usage',
        label: 'Reference usage',
        cell: (a) => {
          const summary = formatReferenceUsageSummary(a);
          if (!summary) return '—';
          return (
            <Box sx={{ display: 'grid', gap: 0.5, maxWidth: 180 }}>
              <StatusBadge label={summary.label} semantic={summary.semantic} />
              {summary.detail ? (
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3 }}>
                  {summary.detail}
                </Typography>
              ) : null}
            </Box>
          );
        },
      },
      {
        id: 'results_found',
        label: 'Results found',
        align: 'right',
        cell: (a) => (typeof a.positions_count === 'number' ? a.positions_count : '—'),
      },
      {
        id: 'pending_review',
        label: 'Pending review',
        align: 'right',
        cell: (a) => (typeof a.pending_review_positions_count === 'number' ? a.pending_review_positions_count : '—'),
      },
      {
        id: 'last_updated',
        label: 'Last updated',
        cell: (a) => formatDate(a.last_activity_at ?? a.updated_at),
      },
      {
        id: 'actions',
        label: 'Actions',
        align: 'right',
        width: 56,
        cell: (a) => {
          const processState = getProcessAisleMenuState(a);
          return (
            <RowActionMenu
              ariaLabel={`Actions for aisle ${a.code}`}
              items={[
                {
                  id: 'upload_assets',
                  label: uploadingAisleId === a.id ? 'Uploading…' : 'Upload assets',
                  onClick: () => handleUploadClick(a.id),
                  disabled: uploadingAisleId === a.id,
                },
                {
                  id: 'process',
                  label: processingAisleId === a.id ? 'Starting…' : 'Process aisle',
                  onClick: () => openProcessDialogForAisle(a.id, a.code),
                  disabled: processState.disabled,
                  disabledReason: processState.disabledReason,
                },
                ...(a.latest_job
                  ? [
                      {
                        id: 'log',
                        label: 'View job details',
                        onClick: () =>
                          setJobDialog({
                            aisleId: a.id,
                            jobId: a.latest_job!.id,
                            aisleCode: a.code,
                          }),
                      },
                    ]
                  : []),
              ]}
            />
          );
        },
      },
    ];
  }, [
    aislesQuery.data,
    aislesQuery.isLoading,
    getProcessAisleMenuState,
    inventoryId,
    navigate,
    openProcessDialogForAisle,
    processingAisleId,
    uploadingAisleId,
  ]);

  if (inventoryLoading && !inventory) {
    return (
      <>
        <LoadingBlock />
      </>
    );
  }

  if (inventoryError && !inventory) {
    return (
      <>
        <ErrorAlert message={inventoryError} onRetry={() => inventoryQuery.refetch()} />
        <Button sx={{ mt: 2 }} onClick={() => navigate('/inventories')}>
          Back to list
        </Button>
      </>
    );
  }

  return (
    <>
      {inventory && (
        <>
          <PageHeader
            breadcrumbs={[{ label: 'Inventories', to: '/inventories' }]}
            title={inventory.name}
            subtitle={
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
                  <StatusBadge
                    label={formatInventoryStatusLabel(String(inventory.status))}
                    semantic={inventoryStatusToBadgeSemantic(String(inventory.status))}
                  />
                </Box>
                <Box component="span" sx={{ color: 'text.secondary', typography: 'caption' }}>
                  Created {formatDate(inventory.created_at ?? undefined)}
                </Box>
              </Box>
            }
            actions={
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setReferenceImagesOpen(true)}
                >
                  Reference images
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  disabled={!inventoryId || exportingCsv}
                  onClick={async () => {
                    if (!inventoryId) return;
                    setExportingCsv(true);
                    try {
                      await exportInventoryResultsCsv(inventoryId);
                    } catch (e) {
                      const err = e instanceof ApiError ? e : new ApiError(String(e));
                      showSnackbar(getApiErrorMessage(err, 'Export failed'), 'error');
                    } finally {
                      setExportingCsv(false);
                    }
                  }}
                >
                  {exportingCsv ? 'Exporting…' : 'Export CSV'}
                </Button>
                <Button variant="contained" size="small" onClick={() => setCreateAisleOpen(true)}>
                  Create aisle
                </Button>
              </Box>
            }
          />
          <Box sx={{ display: 'grid', gap: 2 }}>
            {processError ? (
              <Box data-testid="inventory-process-error">
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  Starting processing
                </Typography>
                <ErrorAlert message={processError} onClose={() => setProcessError(null)} />
              </Box>
            ) : null}

            {uploadError ? (
              <Box data-testid="inventory-upload-error">
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  Asset upload
                </Typography>
                <ErrorAlert message={uploadError} onClose={() => setUploadError(null)} />
              </Box>
            ) : null}

            {aislesError ? <ErrorAlert message={aislesError} onRetry={() => aislesQuery.refetch()} /> : null}

            <SectionCard
              title="Aisles"
              subtitle="Operational queue for this inventory."
              actions={
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => aislesQuery.refetch()}
                  disabled={aislesLoading}
                >
                  Refresh
                </Button>
              }
              variant="elevation"
              elevation={1}
            >
              <input
                type="file"
                ref={fileInputRef}
                accept="image/*,video/*"
                multiple
                style={{ display: 'none' }}
                onChange={handleFileInputChange}
              />
              <DataTable<Aisle>
                rows={aisles}
                rowKey={(a) => a.id}
                columns={aisleColumns}
                loading={aislesLoading}
                onRowClick={(a) => navigate(pathToAislePositions(inventoryId ?? '', a.id))}
                emptyState={{
                  title: 'No aisles yet',
                  message: 'Create an aisle to start processing.',
                  action: (
                    <Button variant="contained" onClick={() => setCreateAisleOpen(true)}>
                      Create aisle
                    </Button>
                  ),
                }}
              />
            </SectionCard>
          </Box>
        </>
      )}

      <Dialog open={Boolean(processDialog)} onClose={closeProcessDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          Start processing{processDialog ? ` — Aisle ${processDialog.aisleCode}` : ''}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Choose provider, model, and prompt profile. &quot;Default (server)&quot; for provider uses{' '}
              {processingProviderOptsQuery.data?.default_provider_key ?? '…'}. Omitting model uses that
              provider&apos;s default model (see the Model dropdown). Omitting prompt uses{' '}
              {processingProviderOptsQuery.data?.default_prompt_key ?? '…'}.
            </Typography>
            <FormControl fullWidth size="small" disabled={processingProviderOptsQuery.isLoading}>
              <InputLabel id="process-provider-label">Provider</InputLabel>
              <Select
                labelId="process-provider-label"
                label="Provider"
                value={processProviderKey}
                onChange={(e) => setProcessProviderKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>Default (server)</em>
                </MenuItem>
                {(processingProviderOptsQuery.data?.providers ?? []).map((p) => (
                  <MenuItem key={p.key} value={p.key}>
                    {p.label}
                    {p.execution_mode === 'transitional_bridge' ? ' (transitional)' : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl
              fullWidth
              size="small"
              disabled={
                processingProviderOptsQuery.isLoading || !providerConfigForProcess?.models?.length
              }
            >
              <InputLabel id="process-model-label">Model</InputLabel>
              <Select
                labelId="process-model-label"
                label="Model"
                value={processModelKey}
                onChange={(e) => setProcessModelKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>
                    Default (
                    {providerConfigForProcess?.default_model ??
                      processingProviderOptsQuery.data?.providers?.find(
                        (p) => p.key === (processingProviderOptsQuery.data?.default_provider_key ?? '')
                      )?.default_model ??
                      '…'}
                    )
                  </em>
                </MenuItem>
                {(providerConfigForProcess?.models ?? []).map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth size="small" disabled={processingProviderOptsQuery.isLoading}>
              <InputLabel id="process-prompt-label">Prompt profile</InputLabel>
              <Select
                labelId="process-prompt-label"
                label="Prompt profile"
                value={processPromptKey}
                onChange={(e) => setProcessPromptKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>Default ({processingProviderOptsQuery.data?.default_prompt_key ?? '…'})</em>
                </MenuItem>
                {(processingProviderOptsQuery.data?.prompt_profiles ?? []).map((p) => (
                  <MenuItem key={p.key} value={p.key}>
                    {p.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {processingProviderOptsQuery.isError ? (
              <Typography variant="caption" color="error">
                {getApiErrorMessage(processingProviderOptsQuery.error, 'Could not load provider list')}
              </Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeProcessDialog}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void confirmProcessDialog()}
            disabled={
              processingAisleId === processDialog?.aisleId ||
              (processingProviderOptsQuery.isLoading && processProviderKey.trim() !== '')
            }
          >
            {processingAisleId === processDialog?.aisleId ? 'Starting…' : 'Start'}
          </Button>
        </DialogActions>
      </Dialog>

      <CreateAisleDialog
        open={createAisleOpen}
        inventoryId={inventoryId ?? ''}
        onClose={() => setCreateAisleOpen(false)}
        onSuccess={handleCreateAisleSuccess}
        existingAisleCodes={aisles.map((a) => a.code)}
        createAisleFn={createAisleMutation.mutateAsync}
      />

      <ReferenceImagesDrawer
        inventoryId={inventoryId ?? ''}
        open={referenceImagesOpen}
        onClose={handleCloseReferenceImages}
        items={visualReferences}
        isLoading={visualReferencesQuery.isLoading}
        errorMessage={visualReferencesError}
        onRetry={() => visualReferencesQuery.refetch()}
        onUpload={(files) => uploadReferenceImagesMutation.mutateAsync(files)}
        isUploading={uploadReferenceImagesMutation.isPending}
        uploadError={
          uploadReferenceImagesMutation.isError && uploadReferenceImagesMutation.error
            ? getApiErrorMessage(uploadReferenceImagesMutation.error, 'Failed to upload reference images')
            : null
        }
        onDelete={(referenceId) => deleteReferenceImageMutation.mutateAsync(referenceId)}
        isDeleting={deleteReferenceImageMutation.isPending}
        deleteError={
          deleteReferenceImageMutation.isError && deleteReferenceImageMutation.error
            ? getApiErrorMessage(deleteReferenceImageMutation.error, 'Failed to delete reference image')
            : null
        }
        onReplace={(referenceId, file) => replaceReferenceImageMutation.mutateAsync({ referenceId, file })}
        isReplacing={replaceReferenceImageMutation.isPending}
        replaceError={
          replaceReferenceImageMutation.isError && replaceReferenceImageMutation.error
            ? getApiErrorMessage(replaceReferenceImageMutation.error, 'Failed to replace reference image')
            : null
        }
      />

      <Dialog
        open={Boolean(jobDialog)}
        onClose={() => setJobDialog(null)}
        maxWidth="sm"
        fullWidth
        scroll="paper"
      >
        <DialogTitle>
          Job details {jobDialog ? `— Aisle ${jobDialog.aisleCode}` : ''}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                {selectedJob ? (
                  <StatusBadge
                    label={getJobStatusLabel(selectedJob.status)}
                    semantic={jobStatusToBadgeSemantic(selectedJob.status)}
                  />
                ) : null}
                {selectedJob?.attempt_count ? (
                  <Typography variant="body2" color="text.secondary">
                    Attempt {selectedJob.attempt_count}
                  </Typography>
                ) : null}
                {selectedJob?.retry_of_job_id ? (
                  <Typography variant="body2" color="text.secondary">
                    Retry of job {selectedJob.retry_of_job_id}
                  </Typography>
                ) : null}
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => void refreshJobOperations()}
                  disabled={jobDetailQuery.isFetching || executionLogQuery.isFetching}
                >
                  {jobDetailQuery.isFetching || executionLogQuery.isFetching ? 'Refreshing…' : 'Refresh'}
                </Button>
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
              </Box>
            </Box>

            {jobDetailQuery.error ? (
              <ErrorAlert
                message={getApiErrorMessage(jobDetailQuery.error, 'Failed to load job details')}
                onRetry={() => {
                  void jobDetailQuery.refetch();
                }}
              />
            ) : null}

            <Box sx={{ display: 'grid', gap: 1 }}>
              {metadataRowsForJob(selectedJob, executionLogQuery.data?.events).map((item) => (
                <Box
                  key={item.label}
                  sx={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 180px) 1fr', gap: 1 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    {item.label}
                  </Typography>
                  <Typography variant="body2">{item.value}</Typography>
                </Box>
              ))}
            </Box>

            <Divider />

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Execution log
              </Typography>
              <ExecutionLogPanel
                events={executionLogQuery.data?.events ?? []}
                isLoading={executionLogQuery.isLoading}
                error={executionLogQuery.error}
                emptyMessage="No log entries yet. The job may not have started or the log file is not available."
              />
            </Box>
          </Stack>
        </DialogContent>
      </Dialog>
    </>
  );
}
