/**
 * Canonical review surface (Sprint v3.3) — drawer with detail fetch, evidence viewer, actions, prev/next, audit.
 */

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Button, Collapse, Drawer, IconButton, Typography, Stack } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { ApiError } from '../../../api/types';
import { REVIEW_ACTION_WIRE, type ReviewActionRequest } from '../../../api/types';
import { useResultDetail, getResultNavigationContext } from '../../results';
import { useSubmitReviewAction } from '../../../hooks';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
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
  titleKey,
  children,
}: {
  titleKey: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  return (
    <Box sx={{ mt: 1.5, pt: 1, borderTop: 1, borderColor: 'divider' }}>
      <Button
        size="small"
        onClick={() => setExpanded((e) => !e)}
        sx={{ 
          textTransform: 'uppercase', 
          color: 'text.primary', 
          fontWeight: 800,
          fontSize: '0.65rem',
          letterSpacing: 1.2,
          mb: expanded ? 1.5 : 0, 
          p: 0, 
          minWidth: 0,
          opacity: expanded ? 0.9 : 0.6,
          '&:hover': { opacity: 1, bgcolor: 'transparent' }
        }}
        aria-expanded={expanded}
      >
        {expanded ? t('common.hide') : t('common.show')} {t(titleKey)}
      </Button>
      <Collapse in={expanded} timeout="auto" unmountOnExit>
         <Box sx={{ pb: 2 }}>{children}</Box>
      </Collapse>
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
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [activePositionId, setActivePositionId] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [invalidConfirmOpen, setInvalidConfirmOpen] = useState(false);
  const [invalidConfirmLoading, setInvalidConfirmLoading] = useState(false);
  const [invalidConfirmError, setInvalidConfirmError] = useState<string | null>(null);
  /** Prevents double-submits (e.g. rapid double-clicks) before React flips `isPending`. */
  const reviewMutationInFlightRef = useRef(false);

  const inventoryId = context?.inventoryId ?? '';
  const aisleId = context?.aisleId ?? '';
  const initialPositionId = activePositionId || context?.positionId || '';
  const enabled = open && Boolean(context && initialPositionId && inventoryId && aisleId);

  const { result, isLoading, isError, error, refetch } = useResultDetail(
    inventoryId,
    aisleId,
    initialPositionId,
    { enabled, jobId: context?.jobId, exactPosition: context?.exactPositionDetail }
  );
  const canonicalPositionId =
    !context?.exactPositionDetail && result?.id ? result.id : initialPositionId;

  // Production strategies: queue vs aisle results. (`detail` is reserved — see `ReviewMutationStrategy`.)
  const reviewStrategy =
    context?.returnTo === 'review_queue'
      ? 'reviewQueue'
      : context?.returnTo === 'aisle_results'
        ? 'aisleResults'
        : undefined;
  const reviewMutation = useSubmitReviewAction(inventoryId, aisleId, canonicalPositionId, {
    strategy: reviewStrategy,
  });
  const actionLoading = reviewMutation.isPending;

  const navContext = useMemo(
    () => (context && canonicalPositionId ? getResultNavigationContext(context.resultIds, canonicalPositionId) : null),
    [context, canonicalPositionId]
  );

  /** POST ``job_id`` must match ``positions.job_id`` from loaded detail only (never URL/run_context). */
  const storageJobIdForReview = useMemo(() => {
    const v = result?.storageJobId;
    if (v != null && String(v).trim() !== '') {
      return String(v).trim();
    }
    return null;
  }, [result?.storageJobId]);

  const withReviewJobId = useCallback((body: ReviewActionRequest): ReviewActionRequest => {
    const id = storageJobIdForReview?.trim();
    if (id) {
      return { ...body, job_id: id };
    }
    const { job_id: _omit, ...rest } = body;
    return rest;
  }, [storageJobIdForReview]);

  /**
   * Single path to the review mutation: one `mutateAsync` per user intent.
   * Guards against overlapping calls (double-click, strict-replay edge cases).
   */
  const executeReviewAction = useCallback(
    async (body: ReviewActionRequest, options?: { successMessage?: string }) => {
      if (reviewMutationInFlightRef.current || reviewMutation.isPending) {
        return;
      }
      reviewMutationInFlightRef.current = true;
      setActionError(null);
      try {
        await reviewMutation.mutateAsync(withReviewJobId(body));
        if (options?.successMessage) {
          showSnackbar(options.successMessage, 'success');
        }
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setActionError(resolveApiErrorMessage(err, 'errors.review_action_failed'));
      } finally {
        reviewMutationInFlightRef.current = false;
      }
    },
    [reviewMutation, showSnackbar, withReviewJobId]
  );

  const handleConfirm = useCallback(() => {
    void executeReviewAction(
      { action_type: REVIEW_ACTION_WIRE.CONFIRM },
      { successMessage: t('review.snackbar_confirmed') }
    );
  }, [executeReviewAction, t]);

  const handleUpdateQuantity = useCallback(
    (corrected_quantity: number) => {
      void executeReviewAction(
        { action_type: REVIEW_ACTION_WIRE.UPDATE_QUANTITY, corrected_quantity },
        { successMessage: t('review.snackbar_qty_updated') }
      );
    },
    [executeReviewAction, t]
  );

  const handleUpdateSku = useCallback(
    (sku: string) => {
      void executeReviewAction(
        { action_type: REVIEW_ACTION_WIRE.UPDATE_SKU, sku },
        { successMessage: t('review.snackbar_sku_updated') }
      );
    },
    [executeReviewAction, t]
  );

  const handleUpdatePositionCode = useCallback(
    (position_code: string) => {
      void executeReviewAction(
        { action_type: REVIEW_ACTION_WIRE.UPDATE_POSITION_CODE, position_code },
        { successMessage: t('review.snackbar_position_updated') }
      );
    },
    [executeReviewAction, t]
  );

  const handleMarkImageMismatch = useCallback(() => {
    void executeReviewAction(
      { action_type: REVIEW_ACTION_WIRE.MARK_IMAGE_MISMATCH },
      { successMessage: t('review.snackbar_image_mismatch') }
    );
  }, [executeReviewAction, t]);

  const handleDeleteClick = useCallback(() => {
    setInvalidConfirmError(null);
    setInvalidConfirmOpen(true);
  }, []);

  const handleInvalidConfirm = useCallback(async () => {
    if (reviewMutationInFlightRef.current || reviewMutation.isPending) {
      return;
    }
    reviewMutationInFlightRef.current = true;
    setInvalidConfirmError(null);
    setInvalidConfirmLoading(true);
    try {
      await reviewMutation.mutateAsync(withReviewJobId({ action_type: REVIEW_ACTION_WIRE.DELETE_POSITION }));
      showSnackbar(t('review.mark_invalid_success'), 'success');
      setInvalidConfirmOpen(false);
      onClose(); // Automatically close after invalidation
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setInvalidConfirmError(resolveApiErrorMessage(err, 'errors.invalidate_result'));
    } finally {
      reviewMutationInFlightRef.current = false;
      setInvalidConfirmLoading(false);
    }
  }, [reviewMutation, showSnackbar, t, withReviewJobId]);

  const handleNavigateToResult = useCallback((resultId: string) => {
    setActivePositionId(resultId);
  }, []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? resolveApiErrorMessage(error, 'errors.load_result_detail')
        : String(error)
      : null;

  const detailTitle = result?.sku?.trim() ? result.sku.trim() : t('review.detail_title_fallback');

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
              {t('review.select_result_prompt')}
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: 'background.paper' }}>
            <Box
              sx={{
                flexShrink: 0,
                position: 'sticky',
                top: 0,
                zIndex: 4,
                bgcolor: 'background.paper',
                borderBottom: 1,
                borderColor: 'divider',
                px: 2.5,
                py: 2,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 1,
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5, fontWeight: 700 }}>
                  {t('review.drawer_mode_title')}
                </Typography>
                <Typography component="h1" variant="h5" sx={{ fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
                  {isLoading && !result ? t('common.loading') : detailTitle}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5, fontWeight: 500 }}>
                  {context.inventoryName} · {context.aisleCode}
                </Typography>
              </Box>
              <IconButton 
                aria-label={t('review.quick_drawer_close')} 
                onClick={onClose} 
                size="small" 
                edge="end" 
                sx={{ mt: -0.5 }}
                disabled={actionLoading}
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>

            <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, pb: 2.5, pt: 2 }}>
              {actionError ? (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
                  {actionError}
                </Alert>
              ) : null}

              {enabled && isLoading && !result ? (
                <ResultDetailLoadingState message={t('review.loading_result')} />
              ) : null}

              {errorMessage && !result ? (
                <>
                  <ResultDetailErrorState message={errorMessage} onRetry={() => refetch()} />
                  <Button sx={{ mt: 2 }} size="small" variant="outlined" onClick={onClose}>
                    {t('common.close')}
                  </Button>
                </>
              ) : null}

              {!isLoading && !errorMessage && !result && enabled ? (
                <ResultDetailEmptyState message={t('review.result_not_found')} />
              ) : null}

              {result ? (
                <Stack spacing={3}>
                  <ResultEvidenceViewer result={result} inventoryId={inventoryId} aisleId={aisleId} />

                  <ResultSummaryCard result={result} />

                  <Box sx={{ pt: 2 }}>
                    <ResultReviewActions
                      result={result}
                      actionLoading={actionLoading}
                      readOnly={false}
                      onConfirm={handleConfirm}
                      onUpdateQuantity={handleUpdateQuantity}
                      onUpdateSku={handleUpdateSku}
                      onUpdatePositionCode={handleUpdatePositionCode}
                      onMarkImageMismatch={handleMarkImageMismatch}
                      onDeleteClick={handleDeleteClick}
                    />
                  </Box>

                  {navContext && navContext.total > 1 && (
                    <Box sx={{ pt: 1 }}>
                      <ResultDetailNavigation 
                        context={navContext} 
                        onNavigate={handleNavigateToResult} 
                        disabled={actionLoading}
                      />
                    </Box>
                  )}

                  <Box sx={{ pt: 4 }}>
                    <DrawerCollapsibleSection titleKey="review.section_history">
                      <ResultReviewHistory items={result.reviewHistory} showHeading={false} />
                    </DrawerCollapsibleSection>

                    <DrawerCollapsibleSection titleKey="review.section_technical">
                      <ResultTechnicalMetadata result={result} />
                    </DrawerCollapsibleSection>
                  </Box>
                </Stack>
              ) : null}
            </Box>
          </Box>
        )}
      </Drawer>

      <ConfirmDialog
        open={open && invalidConfirmOpen}
        onClose={() => {
          setInvalidConfirmOpen(false);
          setInvalidConfirmError(null);
        }}
        title={t('review.mark_invalid_title')}
        description={t('review.mark_invalid_description')}
        confirmLabel={t('review.mark_invalid_cta')}
        confirmColor="error"
        loading={invalidConfirmLoading}
        errorMessage={invalidConfirmError}
        onConfirm={() => void handleInvalidConfirm()}
      />
    </>
  );
}
