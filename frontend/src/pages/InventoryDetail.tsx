import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { Aisle } from '../api/types';
import { ApiError } from '../api/types';
import i18n from '../i18n';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../utils/jobStatus';
import { getAisleStatusLabel, aisleStatusToBadgeSemantic } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import { rowMatchesSearchQuery } from '../utils/tableSearch';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import { exportInventoryResultsCsv } from '../api/client';
import {
  DataTable,
  ErrorAlert,
  FilterToolbar,
  LoadingBlock,
  RowActionMenu,
  SectionCard,
  StatusBadge,
  TableSearchField,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import AisleObservabilityDialog from '../components/AisleObservabilityDialog';
import CreateAisleDialog from '../components/CreateAisleDialog';
import ReferenceImagesDrawer from '../components/ReferenceImagesDrawer';
import {
  useInventoryDetail,
  useInventoryVisualReferences,
  useAislesList,
  useProcessingProviderOptions,
  useCreateAisle,
  useStartAisleProcessing,
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
      ? { label: i18n.t('aisle.reference_usage.pending_run_summary'), semantic: 'neutral' }
      : { label: i18n.t('aisle.reference_usage.summary_unavailable'), semantic: 'neutral' };
  }

  const preparedLabel =
    usage.resolved_count === 1
      ? i18n.t('aisle.reference_usage.prepared_one')
      : i18n.t('aisle.reference_usage.prepared_many', { count: usage.resolved_count });
  const sentLabel =
    usage.provider_consumed_count === 1
      ? i18n.t('aisle.reference_usage.sent_one')
      : i18n.t('aisle.reference_usage.sent_many', { count: usage.provider_consumed_count });

  if (usage.resolution_error) {
    return {
      label: i18n.t('aisle.reference_usage.reference_setup_failed'),
      detail: i18n.t('aisle.reference_usage.setup_failed_detail', { prepared: preparedLabel }),
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
      label: i18n.t('aisle.reference_usage.references_not_sent'),
      detail: preparedLabel,
      semantic: 'warning',
    };
  }

  return {
    label: i18n.t('aisle.reference_usage.processed_without_references'),
    semantic: 'neutral',
  };
}

export default function InventoryDetail() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [observabilityDialog, setObservabilityDialog] = useState<{
    aisleId: string;
    aisleCode: string;
    initialSelectedJobId: string | null;
  } | null>(null);
  const [processDialog, setProcessDialog] = useState<{ aisleId: string; aisleCode: string } | null>(null);
  const [processProviderKey, setProcessProviderKey] = useState('');
  const [processModelKey, setProcessModelKey] = useState('');
  const [processPromptKey, setProcessPromptKey] = useState('');
  const [referenceImagesOpen, setReferenceImagesOpen] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [aisleTableSearch, setAisleTableSearch] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadAisleIdRef = useRef<string | null>(null);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const visualReferencesQuery = useInventoryVisualReferences(inventoryId, {
    enabled: Boolean(referenceImagesOpen && inventoryId && inventoryQuery.data),
  });
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });
  const aisles = aislesQuery.data?.items ?? [];
  const filteredAisles = useMemo(
    () => aisles.filter((a) => rowMatchesSearchQuery(aisleTableSearch, [a.code, a.status, a.id])),
    [aisles, aisleTableSearch]
  );
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
  const uploadMutation = useUploadAisleAssetsFlex(inventoryId ?? '');
  const uploadReferenceImagesMutation = useUploadInventoryVisualReferences(inventoryId ?? '');
  const deleteReferenceImageMutation = useDeleteInventoryVisualReference(inventoryId ?? '');
  const replaceReferenceImageMutation = useReplaceInventoryVisualReference(inventoryId ?? '');

  const inventory = inventoryQuery.data ?? null;
  const isProductionInventory = (inventory?.processing_mode ?? 'production') !== 'test';
  const inventoryLoading = inventoryQuery.isLoading;
  const inventoryError =
    inventoryQuery.isError && inventoryQuery.error
      ? inventoryQuery.error instanceof ApiError && inventoryQuery.error.status === 404
        ? t('inventory.not_found')
        : resolveApiErrorMessage(inventoryQuery.error, 'errors.load_inventory')
      : null;
  const aislesLoading = aislesQuery.isLoading;
  const aislesError =
    aislesQuery.isError && aislesQuery.error
      ? resolveApiErrorMessage(aislesQuery.error, 'errors.load_aisles')
      : null;
  const visualReferences = visualReferencesQuery.data?.items ?? [];
  const visualReferencesError =
    visualReferencesQuery.isError && visualReferencesQuery.error
      ? resolveApiErrorMessage(visualReferencesQuery.error, 'errors.load_reference_images')
      : null;

  const handleCreateAisleSuccess = () => {
    showSnackbar(t('aisle.aisle_created_snackbar'), 'success');
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

  const startProcessForAisle = useCallback(
    async (aisleId: string, aisleCode: string) => {
      if (isProductionInventory) {
        setProcessError(null);
        setUploadError(null);
        setProcessingAisleId(aisleId);
        try {
          await processMutation.mutateAsync({
            aisleId,
            providerName: null,
            modelName: null,
            promptKey: null,
          });
          showSnackbar(t('aisle.processing_started_snackbar'), 'success');
          void aislesQuery.refetch();
        } catch (e) {
          const err = e instanceof ApiError ? e : new ApiError(String(e));
          setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
        } finally {
          setProcessingAisleId(null);
        }
        return;
      }
      openProcessDialogForAisle(aisleId, aisleCode);
    },
    [
      aislesQuery,
      isProductionInventory,
      openProcessDialogForAisle,
      processMutation,
      showSnackbar,
      t,
    ]
  );

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
      showSnackbar(t('aisle.processing_started_snackbar'), 'success');
      setProcessDialog(null);
      void aislesQuery.refetch();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
    } finally {
      setProcessingAisleId(null);
    }
  }, [aislesQuery, processDialog, processModelKey, processMutation, processPromptKey, processProviderKey, showSnackbar, t]);

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
            ? t('aisle.upload_error_verify')
            : t('aisle.upload_error_fallback'),
        };
      }
      if (missingAssets) {
        return { disabled, disabledReason: t('aisle.upload_need_image') };
      }
      return { disabled };
    },
    [aislesQuery.data, aislesQuery.isLoading, isAisleProcessingDisabled, t]
  );

  const handleUploadClick = (aisleId: string) => {
    setUploadError(null);
    pendingUploadAisleIdRef.current = aisleId;
    fileInputRef.current?.click();
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
      showSnackbar(t('aisle.assets_uploaded_snackbar', { count: result.assets.length }), 'success');
      void aislesQuery.refetch();
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
      setUploadError(resolveApiErrorMessage(apiErr, 'errors.upload_failed'));
    } finally {
      setUploadingAisleId(null);
    }
  };

  const aisleColumns = useMemo<DataTableColumn<Aisle>[]>(() => {
    return [
      {
        id: 'code',
        label: t('aisle.code_label'),
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
        label: t('aisle.column_aisle_status'),
        cell: (a) => (
          <StatusBadge
            label={getAisleStatusLabel(String(a.status))}
            semantic={aisleStatusToBadgeSemantic(String(a.status))}
          />
        ),
      },
      {
        id: 'assets',
        label: t('aisle.column_assets'),
        align: 'right',
        cell: (a) => (typeof a.assets_count === 'number' ? a.assets_count : t('common.em_dash')),
      },
      {
        id: 'processing',
        label: t('aisle.column_processing'),
        cell: (a) =>
          a.latest_job ? (
            <StatusBadge
              label={getJobStatusLabel(a.latest_job.status)}
              semantic={jobStatusToBadgeSemantic(a.latest_job.status)}
            />
          ) : (
            t('common.em_dash')
          ),
      },
      {
        id: 'run_provider',
        label: t('aisle.column_run_provider'),
        cell: (a) => (a.latest_job?.provider_name ? String(a.latest_job.provider_name) : t('common.em_dash')),
      },
      {
        id: 'run_model',
        label: t('aisle.column_run_model'),
        cell: (a) => (a.latest_job?.model_name ? String(a.latest_job.model_name) : t('common.em_dash')),
      },
      {
        id: 'reference_usage',
        label: t('aisle.column_reference_usage'),
        cell: (a) => {
          const summary = formatReferenceUsageSummary(a);
          if (!summary) return t('common.em_dash');
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
        label: t('aisle.column_results_found'),
        align: 'right',
        cell: (a) => (typeof a.positions_count === 'number' ? a.positions_count : t('common.em_dash')),
      },
      {
        id: 'pending_review',
        label: t('aisle.column_pending_review'),
        align: 'right',
        cell: (a) =>
          typeof a.pending_review_positions_count === 'number'
            ? a.pending_review_positions_count
            : t('common.em_dash'),
      },
      {
        id: 'last_updated',
        label: t('common.last_updated'),
        cell: (a) => formatDate(a.last_activity_at ?? a.updated_at),
      },
      {
        id: 'actions',
        label: t('common.actions'),
        align: 'right',
        width: 56,
        cell: (a) => {
          const processState = getProcessAisleMenuState(a);
          return (
            <RowActionMenu
              ariaLabel={t('aisle.row_actions_a11y', { code: a.code })}
              items={[
                {
                  id: 'upload_assets',
                  label: uploadingAisleId === a.id ? t('common.uploading') : t('aisle.upload_assets'),
                  onClick: () => handleUploadClick(a.id),
                  disabled: uploadingAisleId === a.id,
                },
                {
                  id: 'execution_logs',
                  label: t('aisle.view_logs'),
                  onClick: () =>
                    setObservabilityDialog({
                      aisleId: a.id,
                      aisleCode: a.code,
                      initialSelectedJobId: a.latest_job?.id ?? null,
                    }),
                },
                {
                  id: 'process',
                  label: processingAisleId === a.id ? t('common.starting') : t('aisle.process_aisle'),
                  onClick: () => void startProcessForAisle(a.id, a.code),
                  disabled: processState.disabled,
                  disabledReason: processState.disabledReason,
                },
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
    startProcessForAisle,
    processingAisleId,
    uploadingAisleId,
    t,
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
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
          {t('inventory.back_to_list')}
        </Button>
      </>
    );
  }

  return (
    <>
      {inventory && (
        <>
          <PageHeader
            breadcrumbs={[{ label: t('aisle.breadcrumb_inventories'), to: '/' }]}
            title={inventory.name}
            subtitle={
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
                  <StatusBadge
                    label={formatInventoryStatusLabel(String(inventory.status))}
                    semantic={inventoryStatusToBadgeSemantic(String(inventory.status))}
                  />
                  <StatusBadge
                    label={
                      inventory.processing_mode === 'test'
                        ? t('inventory.processing_mode_test')
                        : t('inventory.processing_mode_production')
                    }
                    semantic={inventory.processing_mode === 'test' ? 'warning' : 'neutral'}
                  />
                </Box>
                {inventory.primary_execution_config ? (
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t('inventory.primary_config_title')}:{' '}
                    {t('inventory.primary_config_summary', {
                      provider: inventory.primary_execution_config.provider_name,
                      model: inventory.primary_execution_config.model_name,
                      prompt: inventory.primary_execution_config.prompt_key,
                    })}
                  </Typography>
                ) : null}
                <Box component="span" sx={{ color: 'text.secondary', typography: 'caption' }}>
                  {t('inventory.created_date_label', {
                    date: formatDate(inventory.created_at ?? undefined),
                  })}
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
                  {t('aisle.visual_refs_title')}
                </Button>
                {inventory.processing_mode === 'test' ? (
                  <Button
                    variant="outlined"
                    size="small"
                    data-testid="inventory-header-compare-runs"
                    onClick={() => navigate(`/inventories/${inventoryId}/analytics/compare`)}
                  >
                    {t('analytics.compare_runs_link')}
                  </Button>
                ) : null}
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
                      showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
                    } finally {
                      setExportingCsv(false);
                    }
                  }}
                >
                  {exportingCsv ? t('common.exporting') : t('aisle.export_csv')}
                </Button>
                <Button variant="contained" size="small" onClick={() => setCreateAisleOpen(true)}>
                  {t('aisle.create')}
                </Button>
              </Box>
            }
          />
          <Box sx={{ display: 'grid', gap: 2 }}>
            {processError ? (
              <Box data-testid="inventory-process-error">
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  {t('aisle.process_error_label')}
                </Typography>
                <ErrorAlert message={processError} onClose={() => setProcessError(null)} />
              </Box>
            ) : null}

            {uploadError ? (
              <Box data-testid="inventory-upload-error">
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  {t('aisle.upload_error_label')}
                </Typography>
                <ErrorAlert message={uploadError} onClose={() => setUploadError(null)} />
              </Box>
            ) : null}

            {aislesError ? <ErrorAlert message={aislesError} onRetry={() => aislesQuery.refetch()} /> : null}

            <SectionCard
              title={t('aisle.list_title')}
              subtitle={t('aisle.list_subtitle')}
              actions={
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => aislesQuery.refetch()}
                  disabled={aislesLoading}
                >
                  {t('common.refresh')}
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
              <FilterToolbar
                onReset={() => setAisleTableSearch('')}
                resetDisabled={!aisleTableSearch.trim()}
              >
                <TableSearchField
                  label={t('table.search_label')}
                  placeholder={t('aisle.search_aisles_placeholder')}
                  value={aisleTableSearch}
                  onChange={setAisleTableSearch}
                  data-testid="inventory-aisles-search"
                />
              </FilterToolbar>
              <DataTable<Aisle>
                rows={filteredAisles}
                rowKey={(a) => a.id}
                columns={aisleColumns}
                loading={aislesLoading}
                onRowClick={(a) => navigate(pathToAislePositions(inventoryId ?? '', a.id))}
                emptyState={
                  aisleTableSearch.trim() && !aislesLoading && aisles.length > 0 && filteredAisles.length === 0
                    ? { message: t('table.empty_no_match') }
                    : {
                        title: t('aisle.empty_table_title'),
                        message: t('aisle.empty_table_message'),
                        action: (
                          <Button variant="contained" onClick={() => setCreateAisleOpen(true)}>
                            {t('aisle.create')}
                          </Button>
                        ),
                      }
                }
              />
            </SectionCard>
          </Box>
        </>
      )}

      <Dialog open={Boolean(processDialog)} onClose={closeProcessDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {processDialog
            ? t('aisle.process_dialog_title_with_aisle', { code: processDialog.aisleCode })
            : t('aisle.process_dialog_title')}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              {t('aisle.process_dialog_help', {
                defaultProvider: processingProviderOptsQuery.data?.default_provider_key ?? '…',
                defaultPrompt: processingProviderOptsQuery.data?.default_prompt_key ?? '…',
              })}
            </Typography>
            <FormControl fullWidth size="small" disabled={processingProviderOptsQuery.isLoading}>
              <InputLabel id="process-provider-label">{t('common.provider')}</InputLabel>
              <Select
                labelId="process-provider-label"
                label={t('common.provider')}
                value={processProviderKey}
                onChange={(e) => setProcessProviderKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>{t('aisle.process_default_server')}</em>
                </MenuItem>
                {(processingProviderOptsQuery.data?.providers ?? []).map((p) => (
                  <MenuItem key={p.key} value={p.key}>
                    {p.label}
                    {p.execution_mode === 'transitional_bridge' ? ` ${t('aisle.execution_mode_transitional')}` : ''}
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
              <InputLabel id="process-model-label">{t('common.model')}</InputLabel>
              <Select
                labelId="process-model-label"
                label={t('common.model')}
                value={processModelKey}
                onChange={(e) => setProcessModelKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>
                    {t('aisle.process_default_model_em', {
                      model:
                        providerConfigForProcess?.default_model ??
                        processingProviderOptsQuery.data?.providers?.find(
                          (p) => p.key === (processingProviderOptsQuery.data?.default_provider_key ?? '')
                        )?.default_model ??
                        '…',
                    })}
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
              <InputLabel id="process-prompt-label">{t('aisle.prompt_profile')}</InputLabel>
              <Select
                labelId="process-prompt-label"
                label={t('aisle.prompt_profile')}
                value={processPromptKey}
                onChange={(e) => setProcessPromptKey(String(e.target.value))}
              >
                <MenuItem value="">
                  <em>
                    {t('aisle.process_default_prompt_em', {
                      prompt: processingProviderOptsQuery.data?.default_prompt_key ?? '…',
                    })}
                  </em>
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
                {resolveApiErrorMessage(processingProviderOptsQuery.error, 'common.provider_list_error')}
              </Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeProcessDialog}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => void confirmProcessDialog()}
            disabled={
              processingAisleId === processDialog?.aisleId ||
              (processingProviderOptsQuery.isLoading && processProviderKey.trim() !== '')
            }
          >
            {processingAisleId === processDialog?.aisleId ? t('common.starting') : t('aisle.process_start')}
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
            ? resolveApiErrorMessage(uploadReferenceImagesMutation.error, 'errors.upload_reference_images')
            : null
        }
        onDelete={(referenceId) => deleteReferenceImageMutation.mutateAsync(referenceId)}
        isDeleting={deleteReferenceImageMutation.isPending}
        deleteError={
          deleteReferenceImageMutation.isError && deleteReferenceImageMutation.error
            ? resolveApiErrorMessage(deleteReferenceImageMutation.error, 'errors.delete_reference_image')
            : null
        }
        onReplace={(referenceId, file) => replaceReferenceImageMutation.mutateAsync({ referenceId, file })}
        isReplacing={replaceReferenceImageMutation.isPending}
        replaceError={
          replaceReferenceImageMutation.isError && replaceReferenceImageMutation.error
            ? resolveApiErrorMessage(replaceReferenceImageMutation.error, 'errors.replace_reference_image')
            : null
        }
      />

      {observabilityDialog && inventoryId ? (
        <AisleObservabilityDialog
          key={`${observabilityDialog.aisleId}-${observabilityDialog.initialSelectedJobId ?? 'none'}`}
          open
          inventoryId={inventoryId}
          aisleId={observabilityDialog.aisleId}
          aisleCode={observabilityDialog.aisleCode}
          initialSelectedJobId={observabilityDialog.initialSelectedJobId}
          onClose={() => setObservabilityDialog(null)}
          onAislesInvalidate={() => aislesQuery.refetch()}
        />
      ) : null}
    </>
  );
}
