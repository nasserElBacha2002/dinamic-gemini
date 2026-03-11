import { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  CircularProgress,
  Alert,
  Chip,
} from '@mui/material';
import type { Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, getJobStatusColor } from '../utils/jobStatus';
import { getAisleStatusLabel, getAisleStatusColor } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import CreateAisleDialog from '../components/CreateAisleDialog';
import {
  useInventoryDetail,
  useAislesList,
  useAisleAssetCounts,
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadAisleIdRef = useRef<string | null>(null);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });
  const aisles = aislesQuery.data ?? [];
  const assetCounts = useAisleAssetCounts(inventoryId, aisles.map((a) => a.id), {
    enabled: Boolean(inventoryId && aisles.length > 0),
  });
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
  const assetCountByAisleId = assetCounts.data ?? {};

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
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (inventoryError && !inventory) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => inventoryQuery.refetch()}>
              Retry
            </Button>
          }
        >
          {inventoryError}
        </Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
          Back to list
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Button sx={{ mb: 2 }} onClick={() => navigate('/')}>
        ← Back to inventories
      </Button>

      {inventory && (
        <>
          <Paper sx={{ p: 2, mb: 3 }}>
            <Typography variant="h6">{inventory.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              Status: <Chip label={inventory.status} size="small" /> — Created:{' '}
              {formatDate(inventory.created_at ?? undefined)}
            </Typography>
          </Paper>

          <Typography variant="h6" sx={{ mb: 1 }}>
            Metrics
          </Typography>
          {metricsLoading ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <CircularProgress size={24} />
              <Typography variant="body2" color="text.secondary">Loading metrics…</Typography>
            </Box>
          ) : metricsError ? (
            <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={() => metricsQuery.refetch()}>Retry</Button>}>
              {metricsError}
            </Alert>
          ) : metrics ? (
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Total positions</Typography>
                    <Typography variant="h6">{metrics.total_positions}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Reviewed</Typography>
                    <Typography variant="h6">{metrics.total_reviewed_positions}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Auto accepted</Typography>
                    <Typography variant="h6">{metrics.auto_accepted_positions}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Corrected</Typography>
                    <Typography variant="h6">{metrics.corrected_positions}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Deleted</Typography>
                    <Typography variant="h6">{metrics.deleted_positions}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">Success rate</Typography>
                    <Typography variant="h6">{metrics.success_rate}%</Typography>
                  </CardContent>
                </Card>
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
            <Alert
              severity="error"
              sx={{ mb: 2 }}
              action={
                <Button color="inherit" size="small" onClick={() => aislesQuery.refetch()}>
                  Retry
                </Button>
              }
            >
              {aislesError}
            </Alert>
          )}

          {aislesLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress size={28} />
            </Box>
          ) : aisles.length === 0 ? (
            <Paper sx={{ p: 3 }}>
              <Typography color="text.secondary">No aisles yet. Create one to get started.</Typography>
            </Paper>
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
                    <TableCell>Created</TableCell>
                    <TableCell>Error</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {aisles.map((aisle) => (
                    <TableRow key={aisle.id}>
                      <TableCell>{aisle.code}</TableCell>
                      <TableCell>
                        <Chip
                          label={getAisleStatusLabel(aisle.status)}
                          size="small"
                          color={getAisleStatusColor(aisle.status)}
                        />
                      </TableCell>
                      <TableCell>
                        {assetCountByAisleId[aisle.id] != null
                          ? `${assetCountByAisleId[aisle.id]} file(s)`
                          : '—'}
                      </TableCell>
                      <TableCell>
                        {aisle.latest_job ? (
                          <Chip
                            label={getJobStatusLabel(aisle.latest_job.status)}
                            size="small"
                            variant="outlined"
                            color={getJobStatusColor(aisle.latest_job.status)}
                          />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        {(aisle.status === 'processed' || aisle.status === 'in_review' || aisle.status === 'completed' || aisle.latest_job?.status === 'succeeded') ? (
                          <Button
                            variant="text"
                            size="small"
                            onClick={() => navigate(pathToAislePositions(inventoryId ?? '', aisle.id))}
                          >
                            View results
                          </Button>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>{formatDate(aisle.created_at)}</TableCell>
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
    </Box>
  );
}
