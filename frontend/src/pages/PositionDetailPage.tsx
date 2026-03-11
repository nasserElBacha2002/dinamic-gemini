import { useState, useCallback, useEffect } from 'react';
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
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Stack,
} from '@mui/material';
import type {
  PositionSummary,
  ProductRecordSummary,
  ReviewActionSummary,
} from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { getPositionStatusLabel, getPositionStatusColor } from '../utils/positionStatus';
import { pathToAislePositions } from '../utils/resultRoutes';
import { usePositionDetail, useSubmitReviewAction } from '../hooks';

/** Per-product quantity and SKU correction forms. */
function ProductReviewForms({
  product,
  onUpdateQuantity,
  onUpdateSku,
  actionLoading,
}: {
  product: ProductRecordSummary;
  onUpdateQuantity: (productId: string, quantity: number) => void;
  onUpdateSku: (productId: string, sku: string, description?: string) => void;
  actionLoading: boolean;
}) {
  const [qty, setQty] = useState<number>(product.corrected_quantity ?? product.detected_quantity);
  const [sku, setSku] = useState(product.sku);
  const [desc, setDesc] = useState(product.description ?? '');

  useEffect(() => {
    setQty(product.corrected_quantity ?? product.detected_quantity);
    setSku(product.sku);
    setDesc(product.description ?? '');
  }, [product.id, product.detected_quantity, product.corrected_quantity, product.sku, product.description]);

  return (
    <Box sx={{ pl: 1, borderLeft: 2, borderColor: 'divider' }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Product: {product.sku} (id: {product.id})
      </Typography>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
        <TextField
          size="small"
          type="number"
          label="Corrected quantity"
          value={qty}
          onChange={(e) => setQty(Number(e.target.value) || 0)}
          inputProps={{ min: 0 }}
          sx={{ width: 120 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateQuantity(product.id, Math.max(0, qty))}
          disabled={actionLoading}
        >
          Update quantity
        </Button>
      </Stack>
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
        <TextField
          size="small"
          label="SKU"
          value={sku}
          onChange={(e) => setSku(e.target.value)}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="Description (optional)"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          sx={{ width: 200 }}
        />
        <Button
          size="small"
          variant="outlined"
          onClick={() => onUpdateSku(product.id, sku, desc || undefined)}
          disabled={actionLoading || !sku.trim()}
        >
          Update SKU
        </Button>
      </Stack>
    </Box>
  );
}

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

/** Human-readable label for review action type. */
function getReviewActionTypeLabel(actionType: string): string {
  const labels: Record<string, string> = {
    confirm: 'Confirm',
    update_quantity: 'Update quantity',
    update_sku: 'Update SKU',
    delete_position: 'Delete position',
  };
  return labels[actionType] ?? actionType;
}

/** One-line summary of before/after for audit display. */
function beforeAfterSummary(action: ReviewActionSummary): string {
  const b = action.before_json ?? {};
  const a = action.after_json ?? {};
  const parts: string[] = [];
  if (b.status !== undefined || a.status !== undefined) {
    parts.push(`status: ${b.status ?? '—'} → ${a.status ?? '—'}`);
  }
  if (action.action_type === 'update_quantity' && (b.corrected_quantity !== undefined || a.corrected_quantity !== undefined)) {
    parts.push(`quantity: ${b.corrected_quantity ?? '—'} → ${a.corrected_quantity ?? '—'}`);
  }
  if (action.action_type === 'update_sku' && (b.sku !== undefined || a.sku !== undefined)) {
    parts.push(`sku: ${b.sku ?? '—'} → ${a.sku ?? '—'}`);
  }
  return parts.length ? parts.join('; ') : '—';
}

/** Review audit history — action type, date, before/after. */
function ReviewHistorySection({ actions }: { actions: ReviewActionSummary[] }) {
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Review history ({actions.length})
      </Typography>
      {actions.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No review actions yet.</Typography>
      ) : (
        <List dense component={Paper} sx={{ mb: 2 }}>
          {actions.map((a) => (
            <ListItem key={a.id}>
              <ListItemText
                primary={getReviewActionTypeLabel(a.action_type)}
                secondary={
                  <>
                    {formatDate(a.created_at)}
                    {a.user_id && ` · ${a.user_id}`}
                    {a.comment && ` · ${a.comment}`}
                    <br />
                    <Typography component="span" variant="caption" color="text.secondary">
                      {beforeAfterSummary(a)}
                    </Typography>
                  </>
                }
              />
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}

export default function PositionDetailPage() {
  const { inventoryId, aisleId, positionId } = useParams<{
    inventoryId: string;
    aisleId: string;
    positionId: string;
  }>();
  const navigate = useNavigate();
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const detailQuery = usePositionDetail(inventoryId, aisleId, positionId);
  const reviewMutation = useSubmitReviewAction(
    inventoryId ?? '',
    aisleId ?? '',
    positionId ?? ''
  );

  const data = detailQuery.data ?? null;
  const loading = detailQuery.isLoading;
  const error =
    detailQuery.isError && detailQuery.error
      ? detailQuery.error instanceof ApiError
        ? getApiErrorMessage(detailQuery.error, 'Failed to load position')
        : String(detailQuery.error)
      : null;
  const actionLoading = reviewMutation.isPending;
  const displayActionError =
    actionError ??
    (reviewMutation.isError && reviewMutation.error
      ? reviewMutation.error instanceof ApiError
        ? getApiErrorMessage(reviewMutation.error, 'Review action failed')
        : String(reviewMutation.error)
      : null);

  const runAction = useCallback(
    async (fn: () => Promise<void>) => {
      setActionError(null);
      try {
        await fn();
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setActionError(getApiErrorMessage(err, 'Review action failed'));
      }
    },
    []
  );

  const handleConfirm = useCallback(() => {
    runAction(() =>
      reviewMutation.mutateAsync({ action_type: 'confirm' })
    );
  }, [runAction, reviewMutation]);

  const handleUpdateQuantity = useCallback(
    (productId: string, corrected_quantity: number) => {
      runAction(() =>
        reviewMutation.mutateAsync({
          action_type: 'update_quantity',
          product_id: productId,
          corrected_quantity,
        })
      );
    },
    [runAction, reviewMutation]
  );

  const handleUpdateSku = useCallback(
    (productId: string, sku: string, description?: string) => {
      runAction(() =>
        reviewMutation.mutateAsync({
          action_type: 'update_sku',
          product_id: productId,
          sku,
          ...(description !== undefined && description !== '' ? { description } : {}),
        })
      );
    },
    [runAction, reviewMutation]
  );

  const handleDeleteClick = useCallback(() => setDeleteConfirmOpen(true), []);
  const handleDeleteConfirmClose = useCallback(() => setDeleteConfirmOpen(false), []);

  const handleDeleteConfirm = useCallback(() => {
    setDeleteConfirmOpen(false);
    runAction(() =>
      reviewMutation.mutateAsync({ action_type: 'delete_position' })
    );
  }, [runAction, reviewMutation]);

  const handleBack = useCallback(() => {
    navigate(pathToAislePositions(inventoryId ?? '', aisleId ?? ''));
  }, [navigate, inventoryId, aisleId]);

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
            <Button color="inherit" size="small" onClick={() => detailQuery.refetch()}>
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
  const review_actions = data.review_actions ?? [];
  const isDeleted = (position.status ?? '').toString().toLowerCase() === 'deleted';

  return (
    <Box sx={{ p: 3, maxWidth: 700, mx: 'auto' }}>
      <Button sx={{ mb: 2 }} onClick={handleBack}>
        ← Back to positions
      </Button>

      <Typography variant="h6" sx={{ mb: 2 }}>
        Position detail
      </Typography>

      <PositionSummaryCard position={position} />

      {displayActionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {displayActionError}
        </Alert>
      )}

      {!isDeleted && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="subtitle1" sx={{ mb: 1 }}>
            Review actions
          </Typography>
          <Stack spacing={2}>
            <Box>
              <Button
                variant="contained"
                color="primary"
                onClick={handleConfirm}
                disabled={actionLoading}
              >
                {actionLoading ? 'Sending…' : 'Confirm position'}
              </Button>
            </Box>
            {products.map((pr) => (
              <ProductReviewForms
                key={pr.id}
                product={pr}
                onUpdateQuantity={handleUpdateQuantity}
                onUpdateSku={handleUpdateSku}
                actionLoading={actionLoading}
              />
            ))}
            <Box>
              <Button
                variant="outlined"
                color="error"
                onClick={handleDeleteClick}
                disabled={actionLoading}
              >
                Delete position
              </Button>
            </Box>
          </Stack>
        </Paper>
      )}

      {isDeleted && (
        <Alert severity="info" sx={{ mb: 2 }}>
          This position is deleted. No further review actions are available.
        </Alert>
      )}

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
                secondary={
                  <>
                    Quantity: {pr.detected_quantity}
                    {pr.corrected_quantity != null ? ` (corrected: ${pr.corrected_quantity})` : ''}
                    {' — '}{(pr.confidence * 100).toFixed(0)}%
                    {pr.description && (
                      <>
                        <br />
                        {pr.description}
                      </>
                    )}
                  </>
                }
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

      <ReviewHistorySection actions={review_actions} />

      <Dialog open={deleteConfirmOpen} onClose={handleDeleteConfirmClose}>
        <DialogTitle>Delete position?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will mark the position as deleted. You can still view it but no further review actions will be available.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteConfirmClose}>Cancel</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained" disabled={actionLoading}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
