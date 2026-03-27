import { useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Button, Dialog, DialogContent, DialogTitle, Typography } from '@mui/material';
import type { Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../utils/jobStatus';
import { getAisleStatusLabel, aisleStatusToBadgeSemantic } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import { exportInventoryResultsCsv } from '../api/client';
import {
  DataTable,
  EmptyState,
  ErrorAlert,
  KpiCard,
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
import {
  useInventoryDetail,
  useAislesList,
  useExecutionLog,
  useInventoryMetrics,
  useCreateAisle,
  useStartAisleProcessing,
  useUploadAisleAssetsFlex,
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

export default function InventoryDetail() {
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [logDialog, setLogDialog] = useState<{ aisleId: string; jobId: string; aisleCode: string } | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadAisleIdRef = useRef<string | null>(null);

  const executionLogQuery = useExecutionLog(
    inventoryId ?? undefined,
    logDialog?.aisleId,
    logDialog?.jobId,
    {
      enabled: Boolean(logDialog),
      refetchInterval: logDialog ? 4000 : false,
    }
  );

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });
  const aisles = aislesQuery.data?.items ?? [];
  const metricsQuery = useInventoryMetrics(inventoryId);

  const createAisleMutation = useCreateAisle(inventoryId ?? '');
  const processMutation = useStartAisleProcessing(inventoryId ?? '');
  const uploadMutation = useUploadAisleAssetsFlex(inventoryId ?? '');

  const inventory = inventoryQuery.data ?? null;
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
  const metrics = metricsQuery.data ?? null;
  const metricsLoading = metricsQuery.isLoading;
  const metricsError =
    metricsQuery.isError && metricsQuery.error
      ? getApiErrorMessage(metricsQuery.error, 'Failed to load metrics')
      : null;

  const handleCreateAisleSuccess = () => {
    showSnackbar('Aisle created', 'success');
    void aislesQuery.refetch();
  };

  const handleStartProcess = async (aisleId: string) => {
    setProcessError(null);
    setUploadError(null);
    setProcessingAisleId(aisleId);
    try {
      await processMutation.mutateAsync(aisleId);
      showSnackbar('Processing started', 'success');
      void aislesQuery.refetch();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(getApiErrorMessage(err, 'Failed to start processing'));
    } finally {
      setProcessingAisleId(null);
    }
  };

  const isAisleProcessingDisabled = (aisle: Aisle): boolean => {
    const status = (aisle.status || '').toLowerCase();
    return status === 'queued' || status === 'processing' || processingAisleId === aisle.id;
  };

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
      showSnackbar(`${result.assets.length} asset(s) uploaded`, 'success');
      void aislesQuery.refetch();
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
      setUploadError(getApiErrorMessage(apiErr, 'Upload failed'));
    } finally {
      setUploadingAisleId(null);
    }
  };

  const aisleKpis = useMemo(() => {
    const totalAisles = aisles.length;
    const processedAisles = aisles.filter((a) => {
      const s = String(a.status || '').toLowerCase();
      return s === 'processed' || s === 'in_review' || s === 'completed';
    }).length;
    const aislesWithErrors = aisles.filter((a) => {
      const s = String(a.status || '').toLowerCase();
      return s === 'failed' || Boolean(a.error_message) || a.latest_job?.status === 'failed';
    }).length;
    const pendingAisles = Math.max(0, totalAisles - processedAisles - aislesWithErrors);
    const pendingReviewResults = aisles.reduce((sum, a) => sum + (a.pending_review_positions_count ?? 0), 0);
    return { totalAisles, processedAisles, pendingAisles, aislesWithErrors, pendingReviewResults };
  }, [aisles]);

  const reviewCompletionRate = useMemo(() => {
    if (!metrics) return null;
    if (!metrics.total_positions) return 0;
    const r = (metrics.total_reviewed_positions / metrics.total_positions) * 100;
    return Number.isFinite(r) ? Math.round(r) : null;
  }, [metrics]);

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
                  onClick: () => void handleStartProcess(a.id),
                  disabled: isAisleProcessingDisabled(a),
                },
                ...(a.latest_job
                  ? [
                      {
                        id: 'log',
                        label: 'View log',
                        onClick: () =>
                          setLogDialog({
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
  }, [handleStartProcess, inventoryId, navigate, processingAisleId, uploadingAisleId]);

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

          <Box
            sx={{
              mb: 2,
              display: 'flex',
              gap: 1.5,
              flexWrap: { xs: 'wrap', md: 'nowrap' },
              overflowX: { xs: 'visible', md: 'auto' },
              pb: { xs: 0, md: 0.5 },
              alignItems: 'stretch',
            }}
          >
            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 180px' } }}>
              <KpiCard label="Total aisles" value={aislesLoading ? '—' : aisleKpis.totalAisles} />
            </Box>
            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 180px' } }}>
              <KpiCard label="Processed aisles" value={aislesLoading ? '—' : aisleKpis.processedAisles} />
            </Box>
            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 180px' } }}>
              <KpiCard label="Pending aisles" value={aislesLoading ? '—' : aisleKpis.pendingAisles} />
            </Box>
            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 180px' } }}>
              <KpiCard label="Aisles with errors" value={aislesLoading ? '—' : aisleKpis.aislesWithErrors} />
            </Box>

            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 260px' } }}>
              <KpiCard
                label="Review completion rate"
                value={metricsLoading ? '—' : reviewCompletionRate == null ? '—' : `${reviewCompletionRate}%`}
                description={metrics ? `${metrics.total_reviewed_positions}/${metrics.total_positions} reviewed` : undefined}
              />
            </Box>

            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 220px' } }}>
              <KpiCard label="Pending review results" value={aislesLoading ? '—' : aisleKpis.pendingReviewResults} />
            </Box>
            <Box sx={{ flex: { xs: '1 1 240px', md: '0 0 220px' } }}>
              <KpiCard
                label="Manual corrections"
                value={metricsLoading ? '—' : metrics ? metrics.corrected_positions : '—'}
              />
            </Box>
          </Box>

          {metricsError ? <ErrorAlert message={metricsError} onRetry={() => metricsQuery.refetch()} /> : null}

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 2fr) minmax(320px, 1fr)' },
              gap: 2,
              alignItems: 'start',
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              {processError ? (
                <Box sx={{ mb: 2 }} data-testid="inventory-process-error">
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    Starting processing
                  </Typography>
                  <ErrorAlert message={processError} onClose={() => setProcessError(null)} />
                </Box>
              ) : null}

              {uploadError ? (
                <Box sx={{ mb: 2 }} data-testid="inventory-upload-error">
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

            <SectionCard title="Activity" subtitle="Timeline and job log shortcuts for this inventory.">
              <Box sx={{ display: 'grid', gap: 1.5 }}>
                <Box>
                  <Box component="div" sx={{ typography: 'subtitle2', fontWeight: 700, mb: 0.75 }}>
                    Recent activity
                  </Box>
                  <EmptyState message="Recent activity will appear here when activity tracking is enabled." />
                </Box>
                <Box sx={{ pt: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
                  <Box component="div" sx={{ typography: 'subtitle2', fontWeight: 700, mb: 0.75 }}>
                    Logs summary
                  </Box>
                  <EmptyState message="Open View log from an aisle’s actions menu for a full job log. A roll-up summary will appear here when available." />
                </Box>
              </Box>
            </SectionCard>
          </Box>
        </>
      )}

      <CreateAisleDialog
        open={createAisleOpen}
        inventoryId={inventoryId ?? ''}
        onClose={() => setCreateAisleOpen(false)}
        onSuccess={handleCreateAisleSuccess}
        existingAisleCodes={aisles.map((a) => a.code)}
        createAisleFn={createAisleMutation.mutateAsync}
      />

      <Dialog
        open={Boolean(logDialog)}
        onClose={() => setLogDialog(null)}
        maxWidth="sm"
        fullWidth
        scroll="paper"
      >
        <DialogTitle>
          Execution log {logDialog ? `— Aisle ${logDialog.aisleCode}` : ''}
        </DialogTitle>
        <DialogContent dividers>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => executionLogQuery.refetch()}
              disabled={executionLogQuery.isFetching}
            >
              {executionLogQuery.isFetching ? 'Refreshing…' : 'Refresh'}
            </Button>
          </Box>
          <ExecutionLogPanel
            events={executionLogQuery.data?.events ?? []}
            isLoading={executionLogQuery.isLoading}
            error={executionLogQuery.error}
            emptyMessage="No log entries yet. The job may not have started or the log file is not available."
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
