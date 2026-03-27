/**
 * Canonical review surface (Sprint v3.3) — drawer with detail fetch, evidence viewer, actions, prev/next, audit.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Alert, Box, Button, Collapse, Drawer, IconButton, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { ApiError } from '../../../api/types';
import { useResultDetail, getResultNavigationContext } from '../../results';
import { useSubmitReviewAction } from '../../../hooks';
import { getApiErrorMessage } from '../../../utils/apiErrors';
import {
  ResultEvidenceViewer,
  ResultSummaryCard,
  ResultReviewActions,
  ResultReviewHistory,
  ResultTechnicalMetadata,
  ResultDetailNavigation,
  ResultDetailLoadingState,
  ResultDetailErrorState,
  ResultDetailEmptyState,
} from '../../results/components/detail';
import type { QuickReviewContext } from '../quickReviewContext';
import { ConfirmDialog, useAppSnackbar } from '../../../components/ui';

function DrawerCollapsibleSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Box sx={{ mt: 1.5, pt: 1, borderTop: 1, borderColor: 'divider' }}>
      <Button
        size="small"
        onClick={() => setExpanded((e) => !e)}
        sx={{ textTransform: 'none', color: 'text.secondary', mb: expanded ? 1 : 0, p: 0, minWidth: 0 }}
        aria-expanded={expanded}
      >
        {expanded ? 'Hide' : 'Show'} {title}
      </Button>
      <Collapse in={expanded}>{children}</Collapse>
    </Box>
  );
}

export interface QuickReviewDrawerProps {
  open: boolean;
  context: QuickReviewContext | null;
  onClose: () => void;
}

export default function QuickReviewDrawer({
  open,
  context,
  onClose,
}: QuickReviewDrawerProps) {
  const { showSnackbar } = useAppSnackbar();
  const [activePositionId, setActivePositionId] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [invalidConfirmOpen, setInvalidConfirmOpen] = useState(false);
  const [invalidConfirmLoading, setInvalidConfirmLoading] = useState(false);

  useEffect(() => {
    if (context?.positionId) setActivePositionId(context.positionId);
  }, [context?.positionId, context?.inventoryId, context?.aisleId]);

  useEffect(() => {
    if (!open) {
      setActionError(null);
      setInvalidConfirmOpen(false);
      setInvalidConfirmLoading(false);
    }
  }, [open]);

  const inventoryId = context?.inventoryId ?? '';
  const aisleId = context?.aisleId ?? '';
  const enabled = open && Boolean(context && activePositionId && inventoryId && aisleId);

  const { result, isLoading, isError, error, refetch } = useResultDetail(
    inventoryId,
    aisleId,
    activePositionId,
    { enabled }
  );

  const reviewMutation = useSubmitReviewAction(inventoryId, aisleId, activePositionId);
  const actionLoading = reviewMutation.isPending;

  const navContext = useMemo(
    () => (context && activePositionId ? getResultNavigationContext(context.resultIds, activePositionId) : null),
    [context, activePositionId]
  );

  const runAction = useCallback(
    async (fn: () => Promise<void>, options?: { successMessage?: string }) => {
      setActionError(null);
      try {
        await fn();
        if (options?.successMessage) {
          showSnackbar(options.successMessage, 'success');
        }
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setActionError(getApiErrorMessage(err, 'Review action failed'));
      }
    },
    [showSnackbar]
  );

  const handleConfirm = useCallback(() => {
    runAction(() => reviewMutation.mutateAsync({ action_type: 'confirm' }), {
      successMessage: 'Result confirmed',
    });
  }, [runAction, reviewMutation]);

  const handleUpdateQuantity = useCallback(
    (corrected_quantity: number) => {
      runAction(() => reviewMutation.mutateAsync({ action_type: 'update_quantity', corrected_quantity }), {
        successMessage: 'Quantity updated',
      });
    },
    [runAction, reviewMutation]
  );

  const handleUpdateSku = useCallback(
    (sku: string) => {
      runAction(() => reviewMutation.mutateAsync({ action_type: 'update_sku', sku }), {
        successMessage: 'SKU updated',
      });
    },
    [runAction, reviewMutation]
  );

  const handleDeleteClick = useCallback(() => setInvalidConfirmOpen(true), []);
  const handleInvalidConfirm = useCallback(async () => {
    setActionError(null);
    setInvalidConfirmLoading(true);
    try {
      await reviewMutation.mutateAsync({ action_type: 'delete_position' });
      showSnackbar('Result marked invalid', 'success');
      setInvalidConfirmOpen(false);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setActionError(getApiErrorMessage(err, 'Could not invalidate result'));
    } finally {
      setInvalidConfirmLoading(false);
    }
  }, [reviewMutation, showSnackbar]);

  const handleNavigateToResult = useCallback((resultId: string) => {
    setActivePositionId(resultId);
  }, []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load result')
        : String(error)
      : null;

  const detailTitle = result?.sku?.trim() ? result.sku.trim() : 'Result';

  return (
    <>
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        PaperProps={{
          sx: {
            width: { xs: '100%', sm: 'min(720px, 96vw)', md: 'min(1040px, min(94vw, 1200px))' },
            maxWidth: '100vw',
            display: 'flex',
            flexDirection: 'column',
            p: 0,
          },
        }}
      >
        {!context ? (
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Select a result to review.
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: 'background.paper' }}>
            <Box
              sx={{
                flexShrink: 0,
                position: 'sticky',
                top: 0,
                zIndex: 3,
                bgcolor: 'background.paper',
                borderBottom: 1,
                borderColor: 'divider',
                px: 2.5,
                py: 1.5,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1,
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
                  Review
                </Typography>
                <Typography component="h1" variant="h6" sx={{ fontWeight: 600, lineHeight: 1.2, mt: 0.25 }}>
                  {isLoading && !result ? 'Loading…' : detailTitle}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  {context.inventoryName} · {context.aisleCode}
                </Typography>
              </Box>
              <IconButton aria-label="Close drawer" onClick={onClose} size="small" edge="end">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>

            <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, pb: 2.5, pt: 2 }}>
              {actionError ? (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
                  {actionError}
                </Alert>
              ) : null}

              {enabled && isLoading && !result ? <ResultDetailLoadingState message="Loading result…" /> : null}

              {errorMessage && !result ? (
                <>
                  <ResultDetailErrorState message={errorMessage} onRetry={() => refetch()} />
                  <Button sx={{ mt: 2 }} size="small" variant="outlined" onClick={onClose}>
                    Close
                  </Button>
                </>
              ) : null}

              {!isLoading && !errorMessage && !result && enabled ? (
                <ResultDetailEmptyState message="Result not found or no longer available." />
              ) : null}

              {result ? (
                <>
                  <ResultEvidenceViewer result={result} inventoryId={inventoryId} aisleId={aisleId} />

                  <Box sx={{ mt: 2 }}>
                    <ResultSummaryCard result={result} embedInDrawer />
                  </Box>

                  <Box sx={{ mt: 2 }}>
                    <ResultReviewActions
                      result={result}
                      actionLoading={actionLoading}
                      onConfirm={handleConfirm}
                      onUpdateQuantity={handleUpdateQuantity}
                      onUpdateSku={handleUpdateSku}
                      onDeleteClick={handleDeleteClick}
                    />
                  </Box>

                  {navContext && navContext.total > 1 ? (
                    <Box sx={{ mt: 2 }}>
                      <ResultDetailNavigation context={navContext} onNavigate={handleNavigateToResult} />
                    </Box>
                  ) : null}

                  <DrawerCollapsibleSection title="review history">
                    <ResultReviewHistory items={result.reviewHistory} showHeading={false} />
                  </DrawerCollapsibleSection>

                  <Box sx={{ mt: 0.5 }}>
                    <ResultTechnicalMetadata result={result} />
                  </Box>
                </>
              ) : null}
            </Box>
          </Box>
        )}
      </Drawer>

      <ConfirmDialog
        open={invalidConfirmOpen}
        onClose={() => setInvalidConfirmOpen(false)}
        title="Mark result invalid?"
        description="This sets the result to invalid review status and removes it from active review work. The record stays visible for audit."
        confirmLabel="Mark invalid"
        confirmColor="error"
        loading={invalidConfirmLoading}
        onConfirm={() => void handleInvalidConfirm()}
      />
    </>
  );
}
