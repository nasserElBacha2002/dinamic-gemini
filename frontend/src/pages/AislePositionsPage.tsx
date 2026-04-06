/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, TextField, Tooltip, Typography } from '@mui/material';
import { exportInventoryResultsCsv, type AislePositionsListQuery } from '../api/client';
import { getApiErrorMessage } from '../utils/apiErrors';
import type { MergeResultItemResponse, RunMergeResponse } from '../api/types';
import { ApiError } from '../api/types';
import { PageHeader } from '../components/shell';
import { FilterToolbar, SectionCard, useAppSnackbar } from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import {
  useInventoryDetail,
  useAislesList,
  useAisleMergeResults,
  useRunAisleMerge,
  useAisleJobsList,
} from '../hooks';
import {
  useResultSummaries,
  computeResultsKpi,
  filterResults,
  sortResultsByPriority,
  getInitialFilterFromReturnState,
  type ResultsFilterKind,
} from '../features/results';
import QuickReviewDrawer from '../features/reviewQueue/components/QuickReviewDrawer';
import type { OpenReviewDrawerPayload, QuickReviewContext } from '../features/reviewQueue/quickReviewContext';
import {
  ResultsQuickFilters,
  ResultsTable,
  ResultsEmptyState,
  ResultsFilteredEmptyState,
  ResultsLoadingState,
  ResultsErrorState,
  AisleRunSelector,
} from '../features/results/components';

/** Client-side filtered table; matches useResultSummaries default. */
const AISLE_RESULTS_LIST_QUERY: AislePositionsListQuery = { page: 1, page_size: 500 };

type MergeCandidateSummary = {
  groupCount: number;
  skuExamples: string[];
};

type MergeResultsSummary = {
  groupCount: number;
  skuCount: number;
  skuExamples: string[];
};

// UI-only heuristic: repeated visible SKUs are a conservative signal that manual merge
// may be useful. This is intentionally lighter than the backend merge domain logic.
function summarizeLikelyMergeCandidates(
  positions: Array<{ sku?: string | null }>
): MergeCandidateSummary {
  const counts = new Map<string, { label: string; count: number }>();
  for (const position of positions) {
    const rawSku = position.sku?.trim();
    if (!rawSku) continue;
    const key = rawSku.toLowerCase();
    const current = counts.get(key);
    if (current) {
      current.count += 1;
    } else {
      counts.set(key, { label: rawSku, count: 1 });
    }
  }
  const repeated = Array.from(counts.values())
    .filter((entry) => entry.count > 1)
    .map((entry) => entry.label);
  return {
    groupCount: repeated.length,
    skuExamples: repeated.slice(0, 3),
  };
}

function summarizeMergeResults(results: MergeResultItemResponse[] | undefined): MergeResultsSummary | null {
  const consolidated = (results ?? []).filter((item) => item.normalized_label_ids.length > 1);
  if (consolidated.length === 0) return null;
  const skuLabels = consolidated
    .map((item) => item.sku?.trim())
    .filter((sku): sku is string => Boolean(sku));
  const uniqueSkuLabels = Array.from(new Set(skuLabels));
  return {
    groupCount: consolidated.length,
    skuCount: uniqueSkuLabels.length,
    skuExamples: uniqueSkuLabels.slice(0, 3),
  };
}

export default function AislePositionsPage() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showSnackbar } = useAppSnackbar();
  const [filter, setFilter] = useState<ResultsFilterKind>(() =>
    getInitialFilterFromReturnState(location.state)
  );
  const [skuSearch, setSkuSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);
  const [quickContext, setQuickContext] = useState<QuickReviewContext | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [lastMergeResponse, setLastMergeResponse] = useState<RunMergeResponse | null>(null);
  const [lastMergeSummary, setLastMergeSummary] = useState<MergeResultsSummary | null>(null);
  const consumedAisleRedirectKey = useRef<string | null>(null);
  const routeIdentityRef = useRef<string>('');
  const mergeMutation = useRunAisleMerge(inventoryId ?? '');

  const jobIdParam = searchParams.get('jobId')?.trim() || null;

  const positionsListQuery = useMemo<AislePositionsListQuery>(
    () => ({
      ...AISLE_RESULTS_LIST_QUERY,
      ...(jobIdParam ? { job_id: jobIdParam } : {}),
    }),
    [jobIdParam]
  );

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const aisleJobsQuery = useAisleJobsList(inventoryId, aisleId, {
    enabled: Boolean(inventoryId && aisleId && inventoryQuery.data),
  });
  const inventory = inventoryQuery.data ?? null;
  const aisle = useMemo(
    () => aislesQuery.data?.items?.find((a) => a.id === aisleId) ?? null,
    [aislesQuery.data?.items, aisleId]
  );

  const {
    results,
    positions: positionsFromQuery,
    isLoading,
    isError,
    error,
    refetch,
    resultJobId,
    resultContextSource,
  } = useResultSummaries(inventoryId, aisleId, { listQuery: positionsListQuery });
  const positions = positionsFromQuery ?? [];
  const mergeResultsQuery = useAisleMergeResults(inventoryId, aisleId, {
    enabled: Boolean(inventoryId && aisleId && results.length > 0),
    jobId: resultJobId,
  });

  const handleRunSelectionChange = useCallback(
    (next: string | null) => {
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (next && next.trim() !== '') {
            p.set('jobId', next.trim());
          } else {
            p.delete('jobId');
          }
          return p;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  /** Authoritative job for merge, detail, and merge-results; from list response, not URL alone. */
  const visibleJobId = resultJobId ?? null;

  useEffect(() => {
    const key = `${inventoryId ?? ''}-${aisleId ?? ''}`;
    if (!inventoryId || !aisleId) return;
    if (routeIdentityRef.current !== '' && routeIdentityRef.current !== key) {
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.delete('jobId');
          return p;
        },
        { replace: true }
      );
    }
    routeIdentityRef.current = key;
  }, [inventoryId, aisleId, setSearchParams]);

  const kpi = useMemo(() => computeResultsKpi(results), [results]);
  const missingEvidenceCount = useMemo(
    () => results.reduce((n, r) => n + (r.hasEvidence ? 0 : 1), 0),
    [results]
  );

  const filteredByKind = useMemo(() => filterResults(results, filter), [results, filter]);

  const filteredBySku = useMemo(() => {
    const q = skuSearch.trim().toLowerCase();
    if (!q) return filteredByKind;
    return filteredByKind.filter((r) => {
      const sku = (r.sku ?? '').trim().toLowerCase();
      const posCode = (r.positionCode ?? '').trim().toLowerCase();
      return sku.includes(q) || posCode.includes(q);
    });
  }, [filteredByKind, skuSearch]);

  const sortedForTable = useMemo(() => sortResultsByPriority(filteredBySku), [filteredBySku]);

  useEffect(() => {
    if (sortedForTable.length === 0) return;
    const pages = Math.max(1, Math.ceil(sortedForTable.length / pageSize));
    if (page > pages) setPage(pages);
  }, [sortedForTable.length, pageSize, page]);

  useEffect(() => {
    setLastMergeResponse(null);
    setLastMergeSummary(null);
  }, [inventoryId, aisleId, jobIdParam]);

  const tableRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return sortedForTable.slice(start, start + pageSize);
  }, [sortedForTable, page, pageSize]);

  const handleResetFilters = useCallback(() => {
    setFilter('all');
    setSkuSearch('');
    setPage(1);
  }, []);

  const positionById = useMemo(() => {
    const m = new Map<string, (typeof positions)[number]>();
    for (const p of positions) {
      m.set(p.id, p);
    }
    return m;
  }, [positions]);

  const handleOpenReview = useCallback(
    (resultId: string) => {
      if (!positionById.has(resultId) || !inventoryId || !aisleId || !inventory) return;
      setQuickContext({
        inventoryId,
        inventoryName: inventory.name,
        aisleCode: aisle?.code ?? '—',
        aisleId,
        positionId: resultId,
        resultIds: sortedForTable.map((r) => r.id),
        returnTo: 'aisle_results',
        filter,
        jobId: visibleJobId ?? undefined,
      });
    },
    [positionById, inventoryId, inventory, aisle?.code, aisleId, sortedForTable, filter, visibleJobId]
  );

  useEffect(() => {
    const raw = location.state as { openReviewDrawer?: OpenReviewDrawerPayload } | null;
    const p = raw?.openReviewDrawer;
    if (!p || p.kind !== 'aisle' || !inventoryId || !aisleId || !inventory) return;
    const key = `${p.positionId}-${inventoryId}-${aisleId}`;
    if (consumedAisleRedirectKey.current === key) return;
    consumedAisleRedirectKey.current = key;
    setQuickContext({
      inventoryId,
      inventoryName: inventory.name,
      aisleCode: aisle?.code ?? '—',
      aisleId,
      positionId: p.positionId,
      resultIds: p.resultIds,
      returnTo: 'aisle_results',
      filter: p.filter ?? filter,
      jobId: p.jobId,
    });
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, inventory, inventoryId, aisleId, aisle, filter, navigate]);

  const handleClearFilterOnly = useCallback(() => setFilter('all'), []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load results')
        : String(error)
      : null;
  const hasResults = !isLoading && results.length > 0;
  const mergeCandidates = useMemo(() => summarizeLikelyMergeCandidates(positions), [positions]);
  const mergeResultsSummary = useMemo(
    () => summarizeMergeResults(mergeResultsQuery.data?.results),
    [mergeResultsQuery.data?.results]
  );
  const mergeButtonVisible = Boolean(inventoryId && aisleId && hasResults);
  const mergeButtonDisabled = mergeMutation.isPending || mergeCandidates.groupCount === 0;
  const mergeDisabledReason =
    mergeCandidates.groupCount === 0 ? 'No repeated SKUs detected in current results' : '';
  const mergeFeedback = useMemo(() => {
    if (lastMergeResponse != null) {
      if (lastMergeResponse.product_records_updated > 0) {
        const summaryText = lastMergeSummary
          ? ` Latest merge consolidated ${lastMergeSummary.groupCount} repeated SKU ${lastMergeSummary.groupCount === 1 ? 'group' : 'groups'}${lastMergeSummary.skuExamples.length > 0 ? ` (${lastMergeSummary.skuExamples.join(', ')})` : ''}.`
          : '';
        return {
          severity: 'success' as const,
          text: `Visible results updated after merge.${summaryText}`,
        };
      }
      return {
        severity: 'info' as const,
        text: 'Merge completed with no visible quantity changes.',
      };
    }
    if (mergeResultsSummary != null) {
      return {
        severity: 'info' as const,
        text: `Latest merge consolidated ${mergeResultsSummary.groupCount} repeated SKU ${mergeResultsSummary.groupCount === 1 ? 'group' : 'groups'}${mergeResultsSummary.skuExamples.length > 0 ? ` (${mergeResultsSummary.skuExamples.join(', ')})` : ''}.`,
      };
    }
    return null;
  }, [lastMergeResponse, lastMergeSummary, mergeResultsSummary]);

  const handleRunMerge = useCallback(async () => {
    if (!inventoryId || !aisleId) return;
    try {
      setLastMergeResponse(null);
      setLastMergeSummary(null);
      const result = await mergeMutation.mutateAsync({
        aisleId,
        jobId: visibleJobId ?? undefined,
      });
      const [, , refreshedMergeResults] = await Promise.all([
        refetch(),
        aislesQuery.refetch(),
        mergeResultsQuery.refetch(),
      ]);
      setLastMergeResponse(result);
      setLastMergeSummary(summarizeMergeResults(refreshedMergeResults.data?.results));
      showSnackbar(
        result.product_records_updated > 0
          ? 'Repeated labels merged'
          : 'Merge completed with no visible quantity changes',
        'success'
      );
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(getApiErrorMessage(err, 'Merge failed'), 'error');
    }
  }, [aisleId, aislesQuery, inventoryId, mergeMutation, mergeResultsQuery, refetch, showSnackbar, visibleJobId]);

  if (!inventoryId || !aisleId) {
    return (
      <>
        <Alert severity="warning">Missing inventory or aisle.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/inventories')}>
          Back to list
        </Button>
      </>
    );
  }

  const breadcrumbs = [
    { label: 'Inventories', to: '/inventories' as const },
    ...(inventory
      ? [{ label: inventory.name, to: `/inventories/${inventoryId}` as const }]
      : []),
    { label: 'Aisle results' },
  ];

  const jobs = aisleJobsQuery.data?.jobs ?? [];
  const unknownUrlJob =
    Boolean(jobIdParam) &&
    aisleJobsQuery.isFetched &&
    !aisleJobsQuery.isFetching &&
    jobs.length > 0 &&
    !jobs.some((j) => j.id === jobIdParam);

  const positionsLoadNotFound =
    isError && error instanceof ApiError && error.status === 404 && Boolean(jobIdParam);

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={aisle?.code ?? 'Aisle'}
        subtitle={inventory?.name ?? (inventoryQuery.isLoading ? 'Loading…' : '—')}
        actions={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
            {mergeButtonVisible ? (
              <Tooltip title={mergeDisabledReason} disableHoverListener={!mergeDisabledReason}>
                <span>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => void handleRunMerge()}
                    disabled={mergeButtonDisabled}
                  >
                    {mergeMutation.isPending ? 'Merging…' : 'Merge repeated labels'}
                  </Button>
                </span>
              </Tooltip>
            ) : null}
            <Button
              size="small"
              variant="outlined"
              disabled={!inventoryId || exportingCsv}
              onClick={async () => {
                if (!inventoryId) return;
                setExportingCsv(true);
                try {
                  await exportInventoryResultsCsv(inventoryId);
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(getApiErrorMessage(err, 'Export failed'), 'error');
                } finally {
                  setExportingCsv(false);
                }
              }}
            >
              {exportingCsv ? 'Exporting…' : 'Export CSV'}
            </Button>
            <Button size="small" variant="outlined" onClick={() => refetch()} disabled={isLoading}>
              Refresh
            </Button>
          </Box>
        }
      />

      {aisleJobsQuery.isLoading || jobs.length > 0 || Boolean(resultContextSource) ? (
        <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          {aisleJobsQuery.isLoading || jobs.length > 0 ? (
            <AisleRunSelector
              operationalJobId={aisleJobsQuery.data?.operational_job_id ?? null}
              jobs={jobs}
              selectedJobId={jobIdParam}
              onChange={handleRunSelectionChange}
              loading={aisleJobsQuery.isLoading}
            />
          ) : null}
          {resultContextSource ? (
            <Typography variant="caption" color="text.secondary">
              Resolved: {resultContextSource}
              {visibleJobId ? ` · job ${visibleJobId.slice(0, 10)}…` : ''}
            </Typography>
          ) : null}
        </Box>
      ) : null}

      {unknownUrlJob ? (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => handleRunSelectionChange(null)}>
              Clear run filter
            </Button>
          }
        >
          This job is not in the recent runs list for this aisle. Loading may fail; clear the filter or pick another
          run.
        </Alert>
      ) : null}

      {positionsLoadNotFound ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => handleRunSelectionChange(null)}>
              Clear run filter
            </Button>
          }
        >
          No data for this run (invalid or removed). Clear the run filter to use the default resolved slice.
        </Alert>
      ) : null}

      {errorMessage ? <ResultsErrorState message={errorMessage} onRetry={() => refetch()} /> : null}

      {!errorMessage && isLoading ? <ResultsLoadingState message="Loading results…" /> : null}

      {!errorMessage && !isLoading && results.length === 0 ? (
        <>
          <Box sx={{ mb: 3, mt: 1 }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              Counted total
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
              {kpi.aisleTotalCounted}
            </Typography>
          </Box>

          <FilterToolbar
            onReset={handleResetFilters}
            resetDisabled={filter === 'all' && !skuSearch.trim()}
          >
            <TextField
              size="small"
              label="Search"
              placeholder="Filter by SKU or position"
              value={skuSearch}
              onChange={(e) => {
                setSkuSearch(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 200 }}
            />
            <ResultsQuickFilters
              value={filter}
              onChange={(v) => {
                setFilter(v);
                setPage(1);
              }}
              counts={{
                all: kpi.total,
                needs_review: kpi.needsReview,
                low_confidence: kpi.lowConfidence,
                qty_zero: kpi.qtyZero,
                invalid_traceability: kpi.invalidTraceability,
                missing_evidence: missingEvidenceCount,
              }}
            />
          </FilterToolbar>
          <ResultsEmptyState message="No results yet. Run processing on this aisle to see results." />
        </>
      ) : null}

      {!errorMessage && !isLoading && results.length > 0 ? (
        <>
          <Box sx={{ mb: 3, mt: 1 }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              Counted total
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
              {kpi.aisleTotalCounted}
            </Typography>
          </Box>

          {mergeFeedback ? (
            <Alert severity={mergeFeedback.severity} sx={{ mb: 2 }}>
              {mergeFeedback.text}
            </Alert>
          ) : null}

          <FilterToolbar
            onReset={handleResetFilters}
            resetDisabled={filter === 'all' && !skuSearch.trim()}
          >
            <TextField
              size="small"
              label="Search"
              placeholder="Filter by SKU or position"
              value={skuSearch}
              onChange={(e) => {
                setSkuSearch(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 200 }}
            />
            <ResultsQuickFilters
              value={filter}
              onChange={(v) => {
                setFilter(v);
                setPage(1);
              }}
              counts={{
                all: kpi.total,
                needs_review: kpi.needsReview,
                low_confidence: kpi.lowConfidence,
                qty_zero: kpi.qtyZero,
                invalid_traceability: kpi.invalidTraceability,
                missing_evidence: missingEvidenceCount,
              }}
            />
          </FilterToolbar>

          {sortedForTable.length === 0 ? (
            <ResultsFilteredEmptyState onClearFilter={handleClearFilterOnly} />
          ) : (
            <SectionCard title="Results">
              <Box sx={{ overflow: 'auto' }}>
                <ResultsTable
                  results={tableRows}
                  onOpenReview={handleOpenReview}
                  pagination={{
                    page,
                    pageSize,
                    totalItems: sortedForTable.length,
                    onPageChange: setPage,
                    onPageSizeChange: setPageSize,
                  }}
                />
              </Box>
            </SectionCard>
          )}
        </>
      ) : null}

      <QuickReviewDrawer
        open={Boolean(quickContext)}
        context={quickContext}
        onClose={() => setQuickContext(null)}
      />
    </>
  );
}
