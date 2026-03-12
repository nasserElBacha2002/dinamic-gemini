/**
 * Epic 3 — Results overview page (Result-centric review list).
 * Epic 5 — Pass navigation state to detail for previous/next; restore filter when returning from detail.
 */

import { useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Button } from '@mui/material';
import { PageLayout } from '../components/ui';
import { pathToPositionDetail } from '../utils/resultRoutes';
import { getApiErrorMessage } from '../utils/apiErrors';
import { ApiError } from '../api/types';
import {
  useResultSummaries,
  computeResultsKpi,
  filterResults,
  getInitialFilterFromReturnState,
  type ResultDetailNavigationState,
  type ResultsFilterKind,
} from '../features/results';
import {
  ResultsOverviewHeader,
  ResultsKpiCards,
  ResultsQuickFilters,
  ResultsTable,
  ResultsEmptyState,
  ResultsFilteredEmptyState,
  ResultsLoadingState,
  ResultsErrorState,
} from '../features/results/components';

export default function AislePositionsPage() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [filter, setFilter] = useState<ResultsFilterKind>(() =>
    getInitialFilterFromReturnState(location.state)
  );

  const { results, isLoading, isError, error, refetch } = useResultSummaries(
    inventoryId,
    aisleId
  );

  const kpi = useMemo(() => computeResultsKpi(results), [results]);
  const filteredResults = useMemo(
    () => filterResults(results, filter),
    [results, filter]
  );

  const handleBack = useCallback(() => {
    navigate(`/inventories/${inventoryId}`);
  }, [navigate, inventoryId]);

  const handleOpenDetail = useCallback(
    (resultId: string) => {
      if (inventoryId && aisleId) {
        const navigationState: ResultDetailNavigationState = {
          resultIds: filteredResults.map((r) => r.id),
          filter,
        };
        navigate(pathToPositionDetail(inventoryId, aisleId, resultId), {
          state: navigationState,
        });
      }
    },
    [navigate, inventoryId, aisleId, filteredResults, filter]
  );

  const handleClearFilter = useCallback(() => setFilter('all'), []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load results')
        : String(error)
      : null;

  if (!inventoryId || !aisleId) {
    return (
      <PageLayout>
        <Alert severity="warning">Missing inventory or aisle.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
          Back to list
        </Button>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <ResultsOverviewHeader
        title="Results"
        context={`Aisle ${aisleId}`}
        onBack={handleBack}
        backLabel="Back to inventory"
      />

      {errorMessage && (
        <ResultsErrorState message={errorMessage} onRetry={() => refetch()} />
      )}

      {!errorMessage && isLoading && (
        <ResultsLoadingState message="Loading results…" />
      )}

      {!errorMessage && !isLoading && results.length === 0 && (
        <ResultsEmptyState message="No results yet. Run processing on this aisle to see results." />
      )}

      {!errorMessage && !isLoading && results.length > 0 && (
        <>
          <ResultsKpiCards kpi={kpi} />
          <ResultsQuickFilters
            value={filter}
            onChange={setFilter}
            counts={{
              all: kpi.total,
              needs_review: kpi.needsReview,
              valid_traceability: kpi.validTraceability,
              non_valid_traceability: kpi.nonValidTraceability,
              qty_zero: kpi.qtyZero,
              low_confidence: kpi.lowConfidence,
            }}
          />
          {filteredResults.length === 0 ? (
            <ResultsFilteredEmptyState onClearFilter={handleClearFilter} />
          ) : (
            <ResultsTable
              results={filteredResults}
              onOpenDetail={handleOpenDetail}
              showUpdatedAt
            />
          )}
        </>
      )}
    </PageLayout>
  );
}
