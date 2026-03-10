import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Paper,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import { getPositionDetail } from '../api/client';
import type { PositionDetailResponse, PositionSummary } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { getPositionStatusLabel, getPositionStatusColor } from '../utils/positionStatus';
import { pathToAislePositions } from '../utils/resultRoutes';

/** Compact summary card for a position (ID, status, confidence, needs review, updated). */
function PositionSummaryCard({ position }: { position: PositionSummary }) {
  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle2" color="text.secondary">
        ID
      </Typography>
      <Typography variant="body1" sx={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
        {position.id}
      </Typography>
      <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
        <Chip
          label={getPositionStatusLabel(position.status)}
          size="small"
          color={getPositionStatusColor(position.status)}
          variant="outlined"
        />
        <Chip label={`${(position.confidence * 100).toFixed(0)}% confidence`} size="small" variant="outlined" />
        {position.needs_review && <Chip label="Needs review" size="small" color="warning" />}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        Updated: {formatDate(position.updated_at)}
      </Typography>
    </Paper>
  );
}

export default function PositionDetailPage() {
  const { inventoryId, aisleId, positionId } = useParams<{
    inventoryId: string;
    aisleId: string;
    positionId: string;
  }>();
  const navigate = useNavigate();
  const cancelledRef = useRef(false);
  const [data, setData] = useState<PositionDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!inventoryId || !aisleId || !positionId) return;
    cancelledRef.current = false;
    setError(null);
    setLoading(true);
    try {
      const res = await getPositionDetail(inventoryId, aisleId, positionId);
      if (!cancelledRef.current) setData(res);
    } catch (e) {
      if (!cancelledRef.current) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setError(getApiErrorMessage(err, 'Failed to load position'));
      }
    } finally {
      if (!cancelledRef.current) setLoading(false);
    }
  }, [inventoryId, aisleId, positionId]);

  useEffect(() => {
    if (!inventoryId || !aisleId || !positionId) {
      setLoading(false);
      return;
    }
    load();
    return () => {
      cancelledRef.current = true;
    };
  }, [load, inventoryId, aisleId, positionId]);

  const handleBack = () => navigate(pathToAislePositions(inventoryId ?? '', aisleId ?? ''));

  if (!inventoryId || !aisleId || !positionId) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Missing inventory, aisle, or position.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>Back to list</Button>
      </Box>
    );
  }

  if (loading && !data) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !data) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => load()}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
        <Button sx={{ mt: 2 }} onClick={handleBack}>Back to positions</Button>
      </Box>
    );
  }

  if (!data) {
    return null;
  }

  const { position, products, evidences } = data;

  return (
    <Box sx={{ p: 3, maxWidth: 700, mx: 'auto' }}>
      <Button sx={{ mb: 2 }} onClick={handleBack}>
        ← Back to positions
      </Button>

      <Typography variant="h6" sx={{ mb: 2 }}>
        Position detail
      </Typography>

      <PositionSummaryCard position={position} />

      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Products ({products.length})
      </Typography>
      {products.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No products.</Typography>
      ) : (
        <List dense component={Paper} sx={{ mb: 2 }}>
          {products.map((pr) => (
            <ListItem key={pr.id}>
              <ListItemText
                primary={pr.sku}
                secondary={`Quantity: ${pr.detected_quantity}${pr.corrected_quantity != null ? ` (corrected: ${pr.corrected_quantity})` : ''} — ${(pr.confidence * 100).toFixed(0)}%`}
              />
            </ListItem>
          ))}
        </List>
      )}

      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Evidence ({evidences.length})
      </Typography>
      {evidences.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No evidence records.</Typography>
      ) : (
        <List dense component={Paper}>
          {evidences.map((e) => (
            <ListItem key={e.id}>
              <ListItemText
                primary={e.is_primary ? 'Primary' : 'Additional'}
                secondary={e.storage_path || e.id}
              />
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}
