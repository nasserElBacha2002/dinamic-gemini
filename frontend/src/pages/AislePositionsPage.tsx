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
import type { PositionSummary } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { getPositionStatusLabel, getPositionStatusColor } from '../utils/positionStatus';
import { pathToPositionDetail } from '../utils/resultRoutes';
import { useAislePositions } from '../hooks';

function displaySku(p: PositionSummary): string {
  if (p.sku != null && p.sku.trim() !== '') return p.sku.trim();
  const code = p.detected_summary_json && typeof p.detected_summary_json === 'object' && 'internal_code' in p.detected_summary_json
    ? p.detected_summary_json.internal_code
    : undefined;
  if (code != null && typeof code === 'string' && code.trim() !== '') return code.trim();
  return '—';
}

function displayDetectedQuantity(p: PositionSummary): string {
  const q = p.detected_quantity;
  if (q != null && typeof q === 'number' && !Number.isNaN(q) && q >= 0) return String(q);
  const j = p.detected_summary_json;
  if (!j || typeof j !== 'object') return '—';
  const raw = (j as Record<string, unknown>).final_quantity ?? (j as Record<string, unknown>).product_label_quantity;
  if (raw !== null && raw !== undefined && typeof raw === 'number' && !Number.isNaN(raw) && raw >= 0) return String(raw);
  if (typeof raw === 'string' && raw.trim() !== '') {
    const n = Number.parseInt(raw, 10);
    if (!Number.isNaN(n) && n >= 0) return String(n);
  }
  return '—';
}

export default function AislePositionsPage() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, error, refetch } = useAislePositions(inventoryId, aisleId);
  const positions = data?.positions ?? [];
  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load positions')
        : String(error)
      : null;

  const handleBack = () => navigate(`/inventories/${inventoryId}`);

  if (!inventoryId || !aisleId) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Missing inventory or aisle.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>Back to list</Button>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      <Button sx={{ mb: 2 }} onClick={handleBack}>
        ← Back to inventory
      </Button>

      <Typography variant="h6" sx={{ mb: 2 }}>
        Aisle results — Positions
      </Typography>

      {errorMessage && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage}
        </Alert>
      )}

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
          <CircularProgress />
        </Box>
      ) : positions.length === 0 ? (
        <Paper sx={{ p: 3 }}>
          <Typography color="text.secondary">
            No positions yet. Run processing on this aisle to see results.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Position ID</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Detected qty</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Confidence</TableCell>
                <TableCell>Needs review</TableCell>
                <TableCell>Updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={p.id}>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                    {p.id.slice(0, 8)}…
                  </TableCell>
                  <TableCell>{displaySku(p)}</TableCell>
                  <TableCell>{displayDetectedQuantity(p)}</TableCell>
                  <TableCell>
                    <Chip
                      label={getPositionStatusLabel(p.status)}
                      size="small"
                      color={getPositionStatusColor(p.status)}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>{(p.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell>{p.needs_review ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{formatDate(p.updated_at)}</TableCell>
                  <TableCell align="right">
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() =>
                        navigate(pathToPositionDetail(inventoryId, aisleId, p.id))
                      }
                    >
                      Detail
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
