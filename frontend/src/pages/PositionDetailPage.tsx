/**
 * Epic 4 — Result Detail page (Result-centric review detail).
 * Epic 5 — Previous/next navigation from list context; preserve filter on back.
 */

import { useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from '@mui/material';
import { PageLayout } from '../components/ui';
import { pathToAislePositions, pathToPositionDetail } from '../utils/resultRoutes';
import { getApiErrorMessage } from '../utils/apiErrors';
import { ApiError } from '../api/types';
import { useResultDetail, getResultNavigationContext, parseResultDetailNavigationState } from '../features/results';
import { useSubmitReviewAction } from '../hooks';
import {
  ResultDetailHeader,
  ResultSummaryCard,
  ResultEvidencePanel,
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
      navState && positionId
        ? getResultNavigationContext(navState.resultIds, positionId)
        : null,
    [navState, positionId]
  );

  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

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
    runAction(() => reviewMutation.mutateAsync({ action_type: 'confirm' }));
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
    runAction(() => reviewMutation.mutateAsync({ action_type: 'delete_position' }));
  }, [runAction, reviewMutation]);

  const handleBack = useCallback(() => {
    // Only filter is restored on return; full list state is not preserved (e.g. scroll/order).
    const returnState =
      navState?.filter != null ? { filter: navState.filter } : undefined;
    navigate(pathToAislePositions(inventoryId ?? '', aisleId ?? ''), {
      state: returnState,
    });
  }, [navigate, inventoryId, aisleId, navState?.filter]);

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

  if (!inventoryId || !aisleId || !positionId) {
    return (
      <PageLayout>
        <Alert severity="warning">Missing inventory, aisle, or position.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
          Back to list
        </Button>
      </PageLayout>
    );
  }

  if (isLoading && !result) {
    return (
      <PageLayout>
        <ResultDetailLoadingState message="Loading result…" />
      </PageLayout>
    );
  }

  if (errorMessage && !result) {
    return (
      <PageLayout>
        <ResultDetailHeader onBack={handleBack} backLabel="Back to results" />
        <ResultDetailErrorState message={errorMessage} onRetry={() => refetch()} />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          Back to results
        </Button>
      </PageLayout>
    );
  }

  if (!result) {
    return (
      <PageLayout>
        <ResultDetailHeader onBack={handleBack} backLabel="Back to results" />
        <ResultDetailEmptyState message="Result not found or no longer available." />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          Back to results
        </Button>
      </PageLayout>
    );
  }

  // Temporary visible-model rule: backend "deleted" maps to reviewStatus INVALID (see mapPositionStatusToReviewStatus).
  const isDeleted = result.reviewStatus === 'INVALID';

  return (
    <PageLayout maxWidth={700}>
      <ResultDetailHeader
        title="Result"
        context={`Aisle ${aisleId}`}
        onBack={handleBack}
        backLabel="Back to results"
      />

      {navContext && (
        <ResultDetailNavigation
          context={navContext}
          onNavigate={handleNavigateToResult}
        />
      )}

      <ResultSummaryCard result={result} />

      {displayActionError && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={() => setActionError(null)}
        >
          {displayActionError}
        </Alert>
      )}

      <ResultEvidencePanel
        result={result}
        inventoryId={inventoryId}
        aisleId={aisleId}
      />

      <ResultReviewActions
        result={result}
        actionLoading={actionLoading}
        onConfirm={handleConfirm}
        onUpdateQuantity={handleUpdateQuantity}
        onUpdateSku={handleUpdateSku}
        onDeleteClick={handleDeleteClick}
      />

      {isDeleted && (
        <Alert severity="info" sx={{ mb: 2 }}>
          This result is deleted. No further review actions are available.
        </Alert>
      )}

      <ResultReviewHistory items={result.reviewHistory} />

      <ResultTechnicalMetadata result={result} />

      <Dialog open={deleteConfirmOpen} onClose={handleDeleteConfirmClose}>
        <DialogTitle>Delete result?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will mark the result as deleted. You can still view it but no
            further review actions will be available.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteConfirmClose}>Cancel</Button>
          <Button
            onClick={handleDeleteConfirm}
            color="error"
            variant="contained"
            disabled={actionLoading}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </PageLayout>
  );
}
