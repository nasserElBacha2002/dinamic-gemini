/**
 * Epic 3 — Results overview page (Result-centric review list).
 * Epic 5 — Pass navigation state to detail for previous/next; restore filter when returning from detail.
 */

import { useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Button, Paper, Typography, Box } from '@mui/material';
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
import { useAisleMergeResults } from '../hooks/usePositions';
import { useRunAisleMerge } from '../hooks/useMutations';
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
  const runMerge = useRunAisleMerge(inventoryId ?? '');
  const mergeResultsQuery = useAisleMergeResults(inventoryId, aisleId);

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
      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Consolidation (optional)
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Run merge as a post-process artifact. This does not overwrite authoritative quantity.
        </Typography>
        <Button
          size="small"
          variant="outlined"
          onClick={() => runMerge.mutate(aisleId)}
          disabled={runMerge.isPending}
        >
          {runMerge.isPending ? 'Running merge…' : 'Run Merge'}
        </Button>
        {runMerge.isSuccess && (
          <Typography variant="caption" display="block" sx={{ mt: 1 }}>
            Merge recompute ({runMerge.data.operation_mode}): raw={runMerge.data.raw_count}, normalized=
            {runMerge.data.normalized_count}, final={runMerge.data.final_count}
          </Typography>
        )}
        {mergeResultsQuery.isError ? (
          <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
            Failed to load merge groups.
          </Typography>
        ) : null}
        {mergeResultsQuery.data?.results?.length ? (
          <Box sx={{ mt: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1, p: 1 }}>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
              Merge groups ({mergeResultsQuery.data.results.length})
            </Typography>
            {mergeResultsQuery.data.results.slice(0, 8).map((r) => (
              <Typography key={r.id} variant="caption" display="block">
                SKU {r.sku ?? '—'} | position {r.position_id ?? '—'} | merged qty {r.merged_quantity} | review{' '}
                {r.review_required ? 'required' : 'not required'} | normalized labels {r.normalized_label_ids.length}
                {r.explanation_summary ? ` | ${r.explanation_summary}` : ''}
              </Typography>
            ))}
          </Box>
        ) : (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            No merge groups computed yet.
          </Typography>
        )}
      </Paper>

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
