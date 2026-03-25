/**
 * Sprint 4.3 — Result Review Detail: two-column decision layout (evidence | summary + actions + nav),
 * then audit history and collapsible technical metadata.
 */

import { useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Grid,
} from '@mui/material';
import { MAIN_CONTENT_MAX_WIDTH_PX } from '../components/shell';
import { SectionCard } from '../components/ui';
import { pathToAislePositions, pathToPositionDetail } from '../utils/resultRoutes';
import { getApiErrorMessage } from '../utils/apiErrors';
import { ApiError } from '../api/types';
import {
  useResultDetail,
  getResultNavigationContext,
  parseResultDetailNavigationState,
} from '../features/results';
import { useSubmitReviewAction, useInventoryDetail, useAislesList } from '../hooks';
import type { PageHeaderBreadcrumb } from '../components/shell';
import {
  ResultDetailHeader,
  ResultSummaryCard,
  ResultEvidenceViewer,
  ResultReviewActions,
  ResultReviewHistory,
  ResultTechnicalMetadata,
  ResultDetailLoadingState,
  ResultDetailErrorState,
  ResultDetailEmptyState,
  ResultDetailNavigation,
} from '../features/results/components/detail';

export default function PositionDetailPage() {
  const { inventoryId, aisleId, positionId } = useParams<{
    inventoryId: string;
    aisleId: string;
    positionId: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();
  const navState = useMemo(
    () => parseResultDetailNavigationState(location.state),
    [location.state]
  );
  const navContext = useMemo(
    () =>
      navState && positionId ? getResultNavigationContext(navState.resultIds, positionId) : null,
    [navState, positionId]
  );

  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const inventoryQuery = useInventoryDetail(inventoryId, {
    enabled: Boolean(inventoryId),
  });
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId) });
  const aisleCode = useMemo(
    () => aislesQuery.data?.items?.find((a) => a.id === aisleId)?.code ?? null,
    [aislesQuery.data?.items, aisleId]
  );

  const { result, isLoading, isError, error, refetch } = useResultDetail(
    inventoryId,
    aisleId,
    positionId
  );
  const reviewMutation = useSubmitReviewAction(
    inventoryId ?? '',
    aisleId ?? '',
    positionId ?? ''
  );

  const actionLoading = reviewMutation.isPending;
  const displayActionError =
    actionError ??
    (reviewMutation.isError && reviewMutation.error
      ? reviewMutation.error instanceof ApiError
        ? getApiErrorMessage(reviewMutation.error, 'Review action failed')
        : String(reviewMutation.error)
      : null);

  const breadcrumbs = useMemo((): PageHeaderBreadcrumb[] => {
    if (!inventoryId) {
      return [{ label: 'Inventories', to: '/inventories' }, { label: 'Result review' }];
    }
    const invName = inventoryQuery.data?.name ?? 'Inventory';
    const base: PageHeaderBreadcrumb[] = [
      { label: 'Inventories', to: '/inventories' },
      { label: invName, to: `/inventories/${inventoryId}` },
    ];
    if (navState?.returnTo === 'review_queue') {
      return [...base, { label: 'Review queue', to: '/review-queue' }, { label: 'Result review' }];
    }
    return [
      ...base,
      { label: 'Aisle results', to: pathToAislePositions(inventoryId, aisleId ?? '') },
      { label: 'Result review' },
    ];
  }, [inventoryId, aisleId, inventoryQuery.data?.name, navState?.returnTo]);

  const runAction = useCallback(async (fn: () => Promise<void>) => {
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setActionError(getApiErrorMessage(err, 'Review action failed'));
    }
  }, []);

  const handleConfirm = useCallback(() => {
    runAction(() => reviewMutation.mutateAsync({ action_type: 'confirm' }));
  }, [runAction, reviewMutation]);

  const handleUpdateQuantity = useCallback(
    (corrected_quantity: number) => {
      if (!result) return;
      runAction(() =>
        reviewMutation.mutateAsync({
          action_type: 'update_quantity',
          corrected_quantity,
        })
      );
    },
    [runAction, reviewMutation, result]
  );

  const handleUpdateSku = useCallback(
    (sku: string) => {
      if (!result) return;
      runAction(() =>
        reviewMutation.mutateAsync({
          action_type: 'update_sku',
          sku,
        })
      );
    },
    [runAction, reviewMutation, result]
  );

  const handleDeleteClick = useCallback(() => setDeleteConfirmOpen(true), []);
  const handleDeleteConfirmClose = useCallback(() => setDeleteConfirmOpen(false), []);

  const handleDeleteConfirm = useCallback(() => {
    setDeleteConfirmOpen(false);
    runAction(() => reviewMutation.mutateAsync({ action_type: 'delete_position' }));
  }, [runAction, reviewMutation]);

  const handleBack = useCallback(() => {
    if (navState?.returnTo === 'review_queue') {
      navigate('/review-queue');
      return;
    }
    const returnState = navState?.filter != null ? { filter: navState.filter } : undefined;
    navigate(pathToAislePositions(inventoryId ?? '', aisleId ?? ''), {
      state: returnState,
    });
  }, [navigate, inventoryId, aisleId, navState?.filter, navState?.returnTo]);

  const handleNavigateToResult = useCallback(
    (resultId: string) => {
      if (!inventoryId || !aisleId) return;
      navigate(pathToPositionDetail(inventoryId, aisleId, resultId), {
        state: navState ?? undefined,
      });
    },
    [navigate, inventoryId, aisleId, navState]
  );

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load result')
        : String(error)
      : null;

  const detailTitle = result?.sku?.trim() ? result.sku.trim() : 'Result';
  const detailSubtitle = (
    <>
      {inventoryQuery.data?.name ?? 'Inventory'}
      {aisleCode ? ` · Aisle ${aisleCode}` : aisleId ? ` · Aisle` : null}
    </>
  );

  if (!inventoryId || !aisleId || !positionId) {
    return (
      <>
        <Alert severity="warning">Missing inventory, aisle, or position.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/inventories')}>
          Back to list
        </Button>
      </>
    );
  }

  if (isLoading && !result) {
    return (
      <>
        <ResultDetailLoadingState message="Loading result…" />
      </>
    );
  }

  if (errorMessage && !result) {
    return (
      <Box sx={{ maxWidth: MAIN_CONTENT_MAX_WIDTH_PX, mx: 'auto', width: '100%' }}>
        <ResultDetailHeader breadcrumbs={breadcrumbs} title="Result" subtitle={detailSubtitle} />
        <ResultDetailErrorState message={errorMessage} onRetry={() => refetch()} />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          {navState?.returnTo === 'review_queue' ? 'Back to review queue' : 'Back to results'}
        </Button>
      </Box>
    );
  }

  if (!result) {
    return (
      <Box sx={{ maxWidth: MAIN_CONTENT_MAX_WIDTH_PX, mx: 'auto', width: '100%' }}>
        <ResultDetailHeader breadcrumbs={breadcrumbs} title="Result" subtitle={detailSubtitle} />
        <ResultDetailEmptyState message="Result not found or no longer available." />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          {navState?.returnTo === 'review_queue' ? 'Back to review queue' : 'Back to results'}
        </Button>
      </Box>
    );
  }

  const isDeleted = result.reviewStatus === 'INVALID';

  return (
    <Box sx={{ maxWidth: MAIN_CONTENT_MAX_WIDTH_PX, mx: 'auto', width: '100%', pb: 4 }}>
      <ResultDetailHeader breadcrumbs={breadcrumbs} title={detailTitle} subtitle={detailSubtitle} />

      <Box sx={{ mb: 1.5 }}>
        <Button size="small" variant="text" onClick={handleBack}>
          ← {navState?.returnTo === 'review_queue' ? 'Review queue' : 'Aisle results'}
        </Button>
      </Box>

      {displayActionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {displayActionError}
        </Alert>
      )}

      <Grid container spacing={2} alignItems="flex-start">
        <Grid item xs={12} md={7} lg={8}>
          <ResultEvidenceViewer result={result} inventoryId={inventoryId} aisleId={aisleId} />
        </Grid>
        <Grid item xs={12} md={5} lg={4}>
          <ResultSummaryCard result={result} />
          <ResultReviewActions
            result={result}
            actionLoading={actionLoading}
            onConfirm={handleConfirm}
            onUpdateQuantity={handleUpdateQuantity}
            onUpdateSku={handleUpdateSku}
            onDeleteClick={handleDeleteClick}
          />
          {navContext && (
            <ResultDetailNavigation context={navContext} onNavigate={handleNavigateToResult} />
          )}
          {isDeleted && (
            <Alert severity="info" sx={{ mt: 1 }}>
              This result is marked invalid. No further review actions are available.
            </Alert>
          )}
        </Grid>
      </Grid>

      <Box sx={{ mt: 3 }}>
        <SectionCard
          title="Review history & audit"
          subtitle="Actions taken on this result, newest events in list order below."
        >
        <ResultReviewHistory items={result.reviewHistory} showHeading={false} />
        <Box sx={{ mt: 2 }}>
          <ResultTechnicalMetadata result={result} />
        </Box>
        </SectionCard>
      </Box>

      <Dialog open={deleteConfirmOpen} onClose={handleDeleteConfirmClose}>
        <DialogTitle>Mark result invalid?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This sets the result to invalid review status and removes it from active review work. You can still
            open this page to read the record and review history.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteConfirmClose}>Cancel</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained" disabled={actionLoading}>
            Mark invalid
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
