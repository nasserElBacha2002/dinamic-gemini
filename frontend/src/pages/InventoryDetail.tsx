import { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Alert,
} from '@mui/material';
import type { Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, getJobStatusColor } from '../utils/jobStatus';
import { getAisleStatusLabel, getAisleStatusColor } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import { LoadingBlock, EmptyState, ErrorAlert, StatCard, StatusChip } from '../components/ui';
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
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [processMessage, setProcessMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [logDialog, setLogDialog] = useState<{ aisleId: string; jobId: string; aisleCode: string } | null>(null);
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
    setCreateAisleOpen(false);
  };

  const handleStartProcess = async (aisleId: string) => {
    setProcessMessage(null);
    setProcessingAisleId(aisleId);
    try {
      await processMutation.mutateAsync(aisleId);
      setProcessMessage({ type: 'success', text: 'Processing started. List refreshed.' });
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessMessage({
        type: 'error',
        text: getApiErrorMessage(err, 'Failed to start processing'),
      });
    } finally {
      setProcessingAisleId(null);
    }
  };

  const isAisleProcessingDisabled = (aisle: Aisle): boolean => {
    const status = (aisle.status || '').toLowerCase();
    return status === 'queued' || status === 'processing' || processingAisleId === aisle.id;
  };

  const handleUploadClick = (aisleId: string) => {
    setUploadMessage(null);
    pendingUploadAisleIdRef.current = aisleId;
    fileInputRef.current?.click();
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const ctx = getUploadContextFromInput(e, pendingUploadAisleIdRef);
    pendingUploadAisleIdRef.current = null;
    e.target.value = '';
    if (!inventoryId || !ctx) return;

    setUploadMessage(null);
    setUploadingAisleId(ctx.aisleId);
    try {
      const result = await uploadMutation.mutateAsync({ aisleId: ctx.aisleId, files: ctx.files });
      setUploadMessage({
        type: 'success',
        text: `${result.assets.length} asset(s) uploaded. List refreshed.`,
      });
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
      setUploadMessage({ type: 'error', text: getApiErrorMessage(apiErr, 'Upload failed') });
    } finally {
      setUploadingAisleId(null);
    }
  };

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
              <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, mt: 0.5 }}>
                <span>Status:</span>
                <StatusChip label={inventory.status} color={getAisleStatusColor(inventory.status)} />
                <span>—</span>
                <span>Created: {formatDate(inventory.created_at ?? undefined)}</span>
              </Box>
            }
          />

          <Typography variant="h6" sx={{ mb: 1 }}>
            Metrics
          </Typography>
          {metricsLoading ? (
            <LoadingBlock message="Loading metrics…" size={24} py={2} sx={{ mb: 2 }} />
          ) : metricsError ? (
            <ErrorAlert message={metricsError} onRetry={() => metricsQuery.refetch()} />
          ) : metrics ? (
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Total positions" value={metrics.total_positions} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Reviewed" value={metrics.total_reviewed_positions} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Auto accepted" value={metrics.auto_accepted_positions} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Corrected" value={metrics.corrected_positions} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Deleted" value={metrics.deleted_positions} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Success rate" value={`${metrics.success_rate}%`} />
              </Grid>
            </Grid>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>No metrics available.</Typography>
          )}

          <Typography variant="h6" sx={{ mb: 1 }}>
            Aisles
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Button variant="contained" size="small" onClick={() => setCreateAisleOpen(true)}>
              Create aisle
            </Button>
            <Button variant="outlined" size="small" sx={{ ml: 1 }} onClick={() => aislesQuery.refetch()} disabled={aislesLoading}>
              Refresh
            </Button>
          </Box>

          {processMessage && (
            <Alert
              severity={processMessage.type}
              sx={{ mb: 2 }}
              onClose={() => setProcessMessage(null)}
            >
              {processMessage.text}
            </Alert>
          )}

          {uploadMessage && (
            <Alert
              severity={uploadMessage.type}
              sx={{ mb: 2 }}
              onClose={() => setUploadMessage(null)}
            >
              {uploadMessage.text}
            </Alert>
          )}

          {aislesError && (
            <ErrorAlert message={aislesError} onRetry={() => aislesQuery.refetch()} />
          )}

          {aislesLoading ? (
            <LoadingBlock py={3} />
          ) : aisles.length === 0 ? (
            <EmptyState message="No aisles yet. Create one to get started." />
          ) : (
            <TableContainer component={Paper}>
              <input
                type="file"
                ref={fileInputRef}
                accept="image/*,video/*"
                multiple
                style={{ display: 'none' }}
                onChange={handleFileInputChange}
              />
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Code</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Assets</TableCell>
                    <TableCell>Job</TableCell>
                    <TableCell>Results</TableCell>
                    <TableCell>Pending review</TableCell>
                    <TableCell>Last activity</TableCell>
                    <TableCell>Error</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {aisles.map((aisle) => (
                    <TableRow key={aisle.id}>
                      <TableCell>{aisle.code}</TableCell>
                      <TableCell>
                        <StatusChip
                          label={getAisleStatusLabel(aisle.status)}
                          color={getAisleStatusColor(aisle.status)}
                        />
                      </TableCell>
                      <TableCell>
                        {typeof aisle.assets_count === 'number'
                          ? `${aisle.assets_count} file(s)`
                          : '—'}
                      </TableCell>
                      <TableCell>
                        {aisle.latest_job ? (
                          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                              <StatusChip
                                label={getJobStatusLabel(aisle.latest_job.status)}
                                color={getJobStatusColor(aisle.latest_job.status)}
                                variant="outlined"
                              />
                              <Button
                              size="small"
                              variant="text"
                              onClick={() =>
                                setLogDialog({
                                  aisleId: aisle.id,
                                  jobId: aisle.latest_job!.id,
                                  aisleCode: aisle.code,
                                })
                              }
                            >
                              Log
                            </Button>
                            </Box>
                            {aisle.latest_job.status === 'failed' && aisle.latest_job.error_message && (
                              <Typography variant="caption" color="error" component="span" sx={{ display: 'block', maxWidth: 280 }} title={aisle.latest_job.error_message}>
                                {aisle.latest_job.error_message}
                              </Typography>
                            )}
                          </Box>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        {(aisle.status === 'processed' || aisle.status === 'in_review' || aisle.status === 'completed' || aisle.latest_job?.status === 'succeeded') ? (
                          <Box component="span" sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                            {typeof aisle.positions_count === 'number' && (
                              <Typography variant="body2" color="text.secondary" component="span">
                                {aisle.positions_count}
                              </Typography>
                            )}
                            <Button
                              variant="contained"
                              size="small"
                              onClick={() => navigate(pathToAislePositions(inventoryId ?? '', aisle.id))}
                            >
                              View results
                            </Button>
                          </Box>
                        ) : typeof aisle.positions_count === 'number' && aisle.positions_count > 0 ? (
                          <Typography variant="body2">{aisle.positions_count}</Typography>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        {typeof aisle.pending_review_positions_count === 'number'
                          ? aisle.pending_review_positions_count
                          : '—'}
                      </TableCell>
                      <TableCell>
                        {formatDate(aisle.last_activity_at ?? aisle.updated_at)}
                      </TableCell>
                      <TableCell>
                        {aisle.error_message ? (
                          <Typography variant="body2" color="error">
                            {aisle.error_message}
                          </Typography>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          variant="outlined"
                          size="small"
                          sx={{ mr: 1 }}
                          disabled={uploadingAisleId === aisle.id}
                          onClick={() => handleUploadClick(aisle.id)}
                        >
                          {uploadingAisleId === aisle.id ? 'Uploading…' : 'Upload'}
                        </Button>
                        <Button
                          variant="outlined"
                          size="small"
                          disabled={isAisleProcessingDisabled(aisle)}
                          onClick={() => handleStartProcess(aisle.id)}
                        >
                          {processingAisleId === aisle.id ? 'Starting…' : 'Process'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      <CreateAisleDialog
        open={createAisleOpen}
        inventoryId={inventoryId ?? ''}
        onClose={() => setCreateAisleOpen(false)}
        onSuccess={handleCreateAisleSuccess}
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
