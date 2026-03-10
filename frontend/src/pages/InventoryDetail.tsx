import { useState, useEffect, useCallback } from 'react';
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
import { getInventory, getAisles, startAisleProcessing } from '../api/client';
import type { Inventory, Aisle } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { getJobStatusLabel, getJobStatusColor } from '../utils/jobStatus';
import { formatDate } from '../utils/formatDate';
import CreateAisleDialog from '../components/CreateAisleDialog';

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

  const loadAisles = useCallback(async () => {
    if (!inventoryId) return;
    setAislesError(null);
    setAislesLoading(true);
    try {
      const data = await getAisles(inventoryId);
      setAisles(data);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setAislesError(getApiErrorMessage(err, 'Failed to load aisles'));
    } finally {
      setAislesLoading(false);
    }
  }, [inventoryId]);

  useEffect(() => {
    if (!inventoryId) return;
    let cancelled = false;
    let inventoryLoaded = false;
    setInventoryError(null);
    setAislesError(null);
    setInventoryLoading(true);
    getInventory(inventoryId)
      .then((inv) => {
        if (cancelled) return;
        inventoryLoaded = true;
        setInventory(inv);
        setInventoryLoading(false);
        setAislesLoading(true);
        return getAisles(inventoryId);
      })
      .then((aislesData) => {
        if (cancelled) return;
        setAisles(aislesData ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
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
      })
      .finally(() => {
        if (!cancelled) setAislesLoading(false);
      });
    return () => {
      cancelled = true;
    };
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
        <Alert severity="error">{inventoryError}</Alert>
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

          {aislesError && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setAislesError(null)}>
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
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Code</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Job</TableCell>
                    <TableCell>Created</TableCell>
                    <TableCell>Error</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {aisles.map((aisle) => (
                    <TableRow key={aisle.id}>
                      <TableCell>{aisle.code}</TableCell>
                      <TableCell>
                        <Chip label={aisle.status} size="small" />
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
