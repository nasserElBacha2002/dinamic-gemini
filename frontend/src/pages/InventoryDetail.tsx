import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
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
import { getInventory, getAisles, startAisleProcessing, uploadAisleAssets, getAisleAssets } from '../api/client';
import type { Inventory, Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, getJobStatusColor } from '../utils/jobStatus';
import { getAisleStatusLabel, getAisleStatusColor } from '../utils/aisleStatus';
import { formatDate } from '../utils/formatDate';
import { pathToAislePositions } from '../utils/resultRoutes';
import CreateAisleDialog from '../components/CreateAisleDialog';

/** Fetches asset counts for the given aisle IDs; used to keep the Assets column in sync. */
async function fetchAssetCountsForAisles(
  inventoryId: string,
  aisleIds: string[]
): Promise<Record<string, number>> {
  if (aisleIds.length === 0) return {};
  const results = await Promise.all(
    aisleIds.map(async (id) => ({ id, count: (await getAisleAssets(inventoryId, id)).length }))
  );
  return Object.fromEntries(results.map((r) => [r.id, r.count]));
}

function getUploadContextFromInput(
  e: React.ChangeEvent<HTMLInputElement>,
  pendingAisleIdRef: React.MutableRefObject<string | null>
): { files: File[]; aisleId: string } | null {
  const aisleId = pendingAisleIdRef.current;
  const files = e.target.files;
  if (!aisleId || !files?.length) return null;
  return { files: Array.from(files), aisleId };
}

async function executeAisleUpload(
  inventoryId: string,
  aisleId: string,
  files: File[]
): Promise<{ ok: true; count: number } | { ok: false; message: string }> {
  try {
    const result = await uploadAisleAssets(inventoryId, aisleId, files);
    return { ok: true, count: result.assets.length };
  } catch (err) {
    const apiErr = err instanceof ApiError ? err : new ApiError(String(err));
    return { ok: false, message: getApiErrorMessage(apiErr, 'Upload failed') };
  }
}

export default function InventoryDetail() {
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(true);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [aisles, setAisles] = useState<Aisle[]>([]);
  const [aislesLoading, setAislesLoading] = useState(false);
  const [aislesError, setAislesError] = useState<string | null>(null);
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [processMessage, setProcessMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [uploadingAisleId, setUploadingAisleId] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [assetCountByAisleId, setAssetCountByAisleId] = useState<Record<string, number>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadAisleIdRef = useRef<string | null>(null);
  const cancelledRef = useRef(false);

  const loadInitial = useCallback(async () => {
    if (!inventoryId) return;
    cancelledRef.current = false;
    setInventoryError(null);
    setAislesError(null);
    setInventoryLoading(true);
    let inventoryLoaded = false;
    try {
      const inv = await getInventory(inventoryId);
      if (cancelledRef.current) return;
      inventoryLoaded = true;
      setInventory(inv);
      setInventoryLoading(false);
      setAislesLoading(true);
      const aislesData = await getAisles(inventoryId);
      if (cancelledRef.current) return;
      const list = aislesData ?? [];
      setAisles(list);
      if (list.length > 0) {
        const counts = await fetchAssetCountsForAisles(inventoryId, list.map((a) => a.id));
        if (!cancelledRef.current) setAssetCountByAisleId(counts);
      } else {
        setAssetCountByAisleId({});
      }
    } catch (e) {
      if (cancelledRef.current) return;
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setInventoryLoading(false);
      setAislesLoading(false);
      if (!inventoryLoaded) {
        if (err.status === 404) {
          setInventoryError('Inventory not found');
          setInventory(null);
        } else {
          setInventoryError(getApiErrorMessage(err, 'Failed to load inventory'));
        }
      } else {
        setAislesError(getApiErrorMessage(err, 'Failed to load aisles'));
      }
    } finally {
      if (!cancelledRef.current) setAislesLoading(false);
    }
  }, [inventoryId]);

  useEffect(() => {
    loadInitial();
    return () => {
      cancelledRef.current = true;
    };
  }, [loadInitial]);

  const loadAisles = useCallback(async () => {
    if (!inventoryId) return;
    setAislesError(null);
    setAislesLoading(true);
    try {
      const data = await getAisles(inventoryId);
      setAisles(data);
      const counts =
        data.length > 0
          ? await fetchAssetCountsForAisles(inventoryId, data.map((a) => a.id))
          : {};
      setAssetCountByAisleId(counts);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setAislesError(getApiErrorMessage(err, 'Failed to load aisles'));
    } finally {
      setAislesLoading(false);
    }
  }, [inventoryId]);

  const handleCreateAisleSuccess = () => {
    setCreateAisleOpen(false);
    loadAisles();
  };

  const handleStartProcess = async (aisleId: string) => {
    if (!inventoryId) return;
    setProcessMessage(null);
    setProcessingAisleId(aisleId);
    try {
      await startAisleProcessing(inventoryId, aisleId);
      await loadAisles();
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
    const result = await executeAisleUpload(inventoryId, ctx.aisleId, ctx.files);
    if (result.ok) {
      await loadAisles();
      setUploadMessage({
        type: 'success',
        text: `${result.count} asset(s) uploaded. List refreshed.`,
      });
    } else {
      setUploadMessage({ type: 'error', text: result.message });
    }
    setUploadingAisleId(null);
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
            <Button color="inherit" size="small" onClick={() => loadInitial()}>
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
            Aisles
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Button variant="contained" size="small" onClick={() => setCreateAisleOpen(true)}>
              Create aisle
            </Button>
            <Button variant="outlined" size="small" sx={{ ml: 1 }} onClick={loadAisles} disabled={aislesLoading}>
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
              onClose={() => setAislesError(null)}
              action={
                <Button color="inherit" size="small" onClick={() => loadAisles()}>
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
      />
    </Box>
  );
}
