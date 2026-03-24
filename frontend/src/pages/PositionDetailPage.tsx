/**
 * Epic 4 — Result Detail page (Result-centric review detail).
 * Epic 5 — Previous/next navigation from list context; preserve filter on back.
 */

import { useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Box, Button, Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions } from '@mui/material';
import { DETAIL_COLUMN_MAX_WIDTH_PX } from '../components/shell/layoutConstants';
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
      <>
        <ResultDetailHeader onBack={handleBack} backLabel="Back to results" />
        <ResultDetailErrorState message={errorMessage} onRetry={() => refetch()} />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          Back to results
        </Button>
      </>
    );
  }

  if (!result) {
    return (
      <>
        <ResultDetailHeader onBack={handleBack} backLabel="Back to results" />
        <ResultDetailEmptyState message="Result not found or no longer available." />
        <Button sx={{ mt: 2 }} onClick={handleBack}>
          Back to results
        </Button>
      </>
    );
  }

  // Temporary visible-model rule: backend "deleted" maps to reviewStatus INVALID (see mapPositionStatusToReviewStatus).
  const isDeleted = result.reviewStatus === 'INVALID';

  return (
    <Box sx={{ maxWidth: DETAIL_COLUMN_MAX_WIDTH_PX, mx: 'auto', width: '100%' }}>
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
    </Box>
  );
}
