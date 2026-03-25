/**
 * Sprint 4.4 — Quick Review Drawer: compact evidence, summary, and real review actions (queue / aisle).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { ApiError } from '../../../api/types';
import { getReferenceImageFileUrl } from '../../../api/client';
import { StatusBadge, TraceabilityChip } from '../../../components/ui';
import { useSubmitReviewAction } from '../../../hooks';
import { getApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import { useEvidenceImageLoad } from '../../results/hooks/useEvidenceImageLoad';
import { mapPositionSummaryToResultSummary } from '../../results/mappers/positionToResult';
import { getCountOriginLabel } from '../../results/utils/countOriginLabel';
import {
  getReviewStatusLabel,
  reviewStatusToBadgeSemantic,
} from '../../results/utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../results/utils/traceabilityDisplay';
import type { QuickReviewContext } from '../quickReviewContext';

export interface QuickReviewDrawerProps {
  open: boolean;
  context: QuickReviewContext | null;
  onClose: () => void;
  onOpenFullReview: () => void;
}

function displaySku(sku: string | null | undefined): string {
  if (sku != null && String(sku).trim() !== '') return String(sku).trim();
  return '—';
}

function displayQtyResolved(result: ReturnType<typeof mapPositionSummaryToResultSummary>): string {
  const v = result.resolvedQty ?? result.detectedQty;
  if (v != null && !Number.isNaN(v) && v >= 0) return String(v);
  return '—';
}

export default function QuickReviewDrawer({
  open,
  context,
  onClose,
  onOpenFullReview,
}: QuickReviewDrawerProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [invalidConfirmOpen, setInvalidConfirmOpen] = useState(false);
  const [qty, setQty] = useState(0);
  const [sku, setSku] = useState('');

  const inventoryId = context?.inventoryId ?? '';
  const aisleId = context?.aisleId ?? '';
  const positionId = context?.position.id ?? '';

  const reviewMutation = useSubmitReviewAction(inventoryId, aisleId, positionId);
  const actionLoading = reviewMutation.isPending;

  const result = useMemo(
    () => (context ? mapPositionSummaryToResultSummary(context.position) : null),
    [context]
  );

  useEffect(() => {
    if (!context) return;
    const r = mapPositionSummaryToResultSummary(context.position);
    setQty(r.correctedQty ?? r.detectedQty ?? 0);
    setSku(r.sku ?? '');
  }, [context]);

  useEffect(() => {
    if (!open) {
      setActionError(null);
      setInvalidConfirmOpen(false);
    }
  }, [open]);

  const sourceImageId = context?.position.source_image_id;
  const assetId = sourceImageId != null && String(sourceImageId).trim() !== '' ? String(sourceImageId).trim() : null;
  const imageUrl =
    context && assetId ? getReferenceImageFileUrl(context.inventoryId, context.aisleId, assetId, null) : null;
  const loadState = useEvidenceImageLoad(imageUrl);

  const hasEvidenceFlag = result?.hasEvidence ?? false;
  const hasRecordOnly = Boolean(hasEvidenceFlag && !assetId);

  const runAction = useCallback(
    async (fn: () => Promise<void>, closeOnSuccess: boolean) => {
      setActionError(null);
      try {
        await fn();
        if (closeOnSuccess) onClose();
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setActionError(getApiErrorMessage(err, 'Review action failed'));
      }
    },
    [onClose]
  );

  const handleConfirm = useCallback(() => {
    runAction(() => reviewMutation.mutateAsync({ action_type: 'confirm' }), true);
  }, [runAction, reviewMutation]);

  const handleUpdateQuantity = useCallback(() => {
    runAction(
      () =>
        reviewMutation.mutateAsync({
          action_type: 'update_quantity',
          corrected_quantity: Math.max(0, qty),
        }),
      true
    );
  }, [runAction, reviewMutation, qty]);

  const handleUpdateSku = useCallback(() => {
    const t = sku.trim();
    if (!t) return;
    runAction(() => reviewMutation.mutateAsync({ action_type: 'update_sku', sku: t }), true);
  }, [runAction, reviewMutation, sku]);

  const handleInvalidConfirm = useCallback(() => {
    setInvalidConfirmOpen(false);
    runAction(() => reviewMutation.mutateAsync({ action_type: 'delete_position' }), true);
  }, [runAction, reviewMutation]);

  const displayMutationError = actionError;

  const isInvalid = result?.reviewStatus === 'INVALID';

  return (
    <>
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        PaperProps={{
          sx: {
            width: { xs: '100%', sm: 440 },
            maxWidth: '100vw',
            display: 'flex',
            flexDirection: 'column',
            p: 0,
          },
        }}
      >
        {!context || !result ? (
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Select a row to review.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
            <Box
              sx={{
                flexShrink: 0,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1,
                px: 2,
                pt: 2,
                pb: 1,
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="subtitle1" component="h2" fontWeight={600}>
                  Quick review
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  {context.inventoryName} · {context.aisleCode}
                </Typography>
              </Box>
              <IconButton aria-label="Close drawer" onClick={onClose} size="small" edge="end">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>

            <Box sx={{ px: 2, pb: 1.5, flex: 1, overflow: 'auto', minHeight: 0 }}>
              {open && displayMutationError ? (
                <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setActionError(null)}>
                  {displayMutationError}
                </Alert>
              ) : null}

              <Box
                sx={{
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  bgcolor: 'grey.50',
                  overflow: 'hidden',
                  mb: 1.5,
                }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pt: 1, display: 'block' }}>
                  Evidence
                </Typography>
                <Box
                  sx={{
                    minHeight: 120,
                    maxHeight: 200,
                    mx: 1,
                    mb: 1,
                    borderRadius: 1,
                    bgcolor: 'grey.100',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    overflow: 'hidden',
                  }}
                >
                  {!hasEvidenceFlag && (
                    <Typography variant="caption" color="text.secondary" sx={{ px: 1, py: 2, textAlign: 'center' }}>
                      No image evidence for this result.
                    </Typography>
                  )}
                  {hasRecordOnly && (
                    <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 2, textAlign: 'center' }}>
                      Evidence is recorded, but no image is available to display here. Use open full review if you need
                      to inspect files.
                    </Typography>
                  )}
                  {assetId && loadState.status === 'loading' && <CircularProgress size={28} />}
                  {assetId && loadState.status === 'loaded' && (
                    <Box
                      component="img"
                      src={loadState.blobUrl}
                      alt={context.position.source_image_original_filename ?? 'Evidence'}
                      sx={{
                        maxWidth: '100%',
                        maxHeight: 180,
                        objectFit: 'contain',
                        display: 'block',
                      }}
                    />
                  )}
                  {assetId && loadState.status === 'error' && (
                    <Typography variant="caption" color="error" sx={{ px: 1.5, py: 1, textAlign: 'center' }}>
                      {loadState.message}
                    </Typography>
                  )}
                </Box>
                {context.position.source_image_original_filename ? (
                  <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pb: 1, display: 'block' }} noWrap>
                    {context.position.source_image_original_filename}
                  </Typography>
                ) : null}
              </Box>

              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                Updated {formatDate(context.position.updated_at)}
              </Typography>

              <Divider sx={{ my: 1.5 }} />

              <Stack spacing={1}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    SKU
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {displaySku(context.position.sku)}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    Quantity
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {displayQtyResolved(result)}
                  </Typography>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Count origin: {getCountOriginLabel(result)}
                </Typography>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    Confidence
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {context.position.confidence != null
                      ? `${(context.position.confidence * 100).toFixed(0)}%`
                      : '—'}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    Traceability
                  </Typography>
                  <TraceabilityChip
                    status={visibleTraceabilityToApiStatus(result.traceabilityStatus)}
                    size="small"
                    variant="outlined"
                  />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    Review status
                  </Typography>
                  <StatusBadge
                    label={getReviewStatusLabel(result.reviewStatus)}
                    semantic={reviewStatusToBadgeSemantic(result.reviewStatus)}
                    variant="outlined"
                  />
                </Box>
              </Stack>

              {!isInvalid ? (
                <>
                  <Divider sx={{ my: 1.5 }} />
                  <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
                    Quick actions
                  </Typography>
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Confirm
                    </Typography>
                    <Button
                      variant="contained"
                      color="primary"
                      fullWidth
                      size="medium"
                      disabled={actionLoading}
                      onClick={handleConfirm}
                      sx={{ mt: 0.5 }}
                    >
                      {actionLoading ? 'Sending…' : 'Confirm result'}
                    </Button>
                  </Box>
                  <Box sx={{ mt: 1.5 }}>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      Corrections
                    </Typography>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                      <TextField
                        size="small"
                        type="number"
                        label="Qty"
                        value={qty}
                        onChange={(e) => setQty(Number(e.target.value) || 0)}
                        inputProps={{ min: 0 }}
                        sx={{ width: 100 }}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={actionLoading}
                        onClick={handleUpdateQuantity}
                      >
                        Update quantity
                      </Button>
                    </Stack>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      <TextField
                        size="small"
                        label="SKU"
                        value={sku}
                        onChange={(e) => setSku(e.target.value)}
                        sx={{ width: 140 }}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={actionLoading || !sku.trim()}
                        onClick={handleUpdateSku}
                      >
                        Update SKU
                      </Button>
                    </Stack>
                  </Box>
                  <Box
                    sx={{
                      mt: 1.5,
                      p: 1.25,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      border: 1,
                      borderColor: 'error.light',
                    }}
                  >
                    <Typography variant="caption" color="error" display="block" fontWeight={600}>
                      Invalidate
                    </Typography>
                    <Button
                      variant="outlined"
                      color="error"
                      size="small"
                      fullWidth
                      disabled={actionLoading}
                      sx={{ mt: 0.75 }}
                      onClick={() => setInvalidConfirmOpen(true)}
                    >
                      Mark result invalid
                    </Button>
                  </Box>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  This result is marked invalid. Use open full review for the full record.
                </Typography>
              )}

              <Divider sx={{ my: 1.5 }} />

              <Button variant="outlined" fullWidth onClick={onOpenFullReview} sx={{ mb: 1 }}>
                Open full review
              </Button>
              <Button variant="text" fullWidth onClick={onClose}>
                Close
              </Button>
            </Box>
          </Box>
        )}
      </Drawer>

      <Dialog open={invalidConfirmOpen} onClose={() => setInvalidConfirmOpen(false)}>
        <DialogTitle>Mark result invalid?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This sets the result to invalid review status and removes it from active review work. You can still open
            full review to read the record.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInvalidConfirmOpen(false)}>Cancel</Button>
          <Button onClick={handleInvalidConfirm} color="error" variant="contained" disabled={actionLoading}>
            Mark invalid
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
