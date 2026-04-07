/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
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
  usePromoteAisleOperationalJob,
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
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [compareJobA, setCompareJobA] = useState('');
  const [compareJobB, setCompareJobB] = useState('');
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [promoteJobId, setPromoteJobId] = useState('');
  const consumedAisleRedirectKey = useRef<string | null>(null);
  const routeIdentityRef = useRef<string>('');
  /** When true, user chose "Default (API resolver)" — keep list request without job_id even if result_job_id repeats. */
  const [preferDefaultSlice, setPreferDefaultSlice] = useState(false);
  const mergeMutation = useRunAisleMerge(inventoryId ?? '');
  const promoteMutation = usePromoteAisleOperationalJob(inventoryId ?? '', aisleId ?? '');

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
  const jobs = aisleJobsQuery.data?.jobs ?? [];
  const operationalJobId = aisleJobsQuery.data?.operational_job_id?.trim() || null;
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
      if (next == null || next === '') {
        setPreferDefaultSlice(true);
      } else {
        setPreferDefaultSlice(false);
      }
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

  const visibleJobSummary = useMemo(
    () => jobs.find((j) => j.id === visibleJobId) ?? null,
    [jobs, visibleJobId]
  );

  const canPromoteCurrentRun = Boolean(
    inventoryId &&
      aisleId &&
      visibleJobId &&
      visibleJobSummary?.status === 'succeeded' &&
      operationalJobId !== visibleJobId
  );

  const openCompareDialog = useCallback(() => {
    const a = visibleJobId ?? jobs[0]?.id ?? '';
    const b =
      jobs.find((j) => j.id !== a)?.id ??
      operationalJobId ??
      '';
    setCompareJobA(a);
    setCompareJobB(b);
    setCompareDialogOpen(true);
  }, [visibleJobId, jobs, operationalJobId]);

  /** Aligns dropdown with the run actually shown: URL pin wins; else backend-resolved id when it appears in the jobs list. */
  const effectiveSelectorJobId = useMemo(() => {
    if (preferDefaultSlice) return null;
    const url = jobIdParam?.trim();
    if (url && jobs.some((j) => j.id === url)) return url;
    if (!url && resultJobId && jobs.some((j) => j.id === resultJobId)) return resultJobId;
    return null;
  }, [preferDefaultSlice, jobIdParam, resultJobId, jobs]);

  useEffect(() => {
    const key = `${inventoryId ?? ''}-${aisleId ?? ''}`;
    if (!inventoryId || !aisleId) return;
    if (routeIdentityRef.current !== '' && routeIdentityRef.current !== key) {
      setPreferDefaultSlice(false);
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

  const reviewReadOnly = Boolean(
    operationalJobId && visibleJobId && operationalJobId !== visibleJobId
  );
  const compareOperationalShortcut =
    Boolean(
      inventoryId &&
        aisleId &&
        operationalJobId &&
        visibleJobId &&
        operationalJobId !== visibleJobId
    );

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
        reviewReadOnly,
      });
    },
    [
      positionById,
      inventoryId,
      inventory,
      aisle?.code,
      aisleId,
      sortedForTable,
      filter,
      visibleJobId,
      reviewReadOnly,
    ]
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
      reviewReadOnly,
    });
    navigate(location.pathname, { replace: true, state: {} });
  }, [
    location.state,
    location.pathname,
    inventory,
    inventoryId,
    aisleId,
    aisle,
    filter,
    navigate,
    reviewReadOnly,
  ]);

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
  const mergeButtonDisabled =
    mergeMutation.isPending || mergeCandidates.groupCount === 0 || reviewReadOnly;
  const mergeDisabledReason = reviewReadOnly
    ? 'Merge is only available on the operational job slice'
    : mergeCandidates.groupCount === 0
      ? 'No repeated SKUs detected in current results'
      : '';
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
        jobId: visibleJobId ?? null,
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
            {jobs.length >= 2 ? (
              <Button size="small" variant="outlined" onClick={openCompareDialog}>
                Compare runs…
              </Button>
            ) : null}
            {compareOperationalShortcut ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() =>
                  navigate(
                    `/inventories/${inventoryId}/aisles/${aisleId}/compare?jobAId=${encodeURIComponent(visibleJobId!)}&jobBId=${encodeURIComponent(operationalJobId!)}`
                  )
                }
              >
                Compare to operational
              </Button>
            ) : null}
            {canPromoteCurrentRun ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  setPromoteJobId(visibleJobId ?? '');
                  setPromoteDialogOpen(true);
                }}
              >
                Promote run to operational…
              </Button>
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
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                void refetch();
                void aisleJobsQuery.refetch();
              }}
              disabled={isLoading}
            >
              Refresh
            </Button>
          </Box>
        }
      />

      {reviewReadOnly ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          You are viewing a non-operational run (read-only review). Operational slice uses job{' '}
          <Typography component="span" variant="body2" sx={{ fontFamily: 'monospace' }}>
            {operationalJobId?.slice(0, 10)}…
          </Typography>
          . Promote a succeeded run to shift editability.
        </Alert>
      ) : null}

      {aisleJobsQuery.isLoading || jobs.length > 0 || Boolean(resultContextSource) ? (
        <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          {aisleJobsQuery.isLoading || jobs.length > 0 ? (
            <AisleRunSelector
              operationalJobId={aisleJobsQuery.data?.operational_job_id ?? null}
              jobs={jobs}
              valueJobId={effectiveSelectorJobId}
              onChange={handleRunSelectionChange}
              loading={aisleJobsQuery.isLoading}
              urlPinned={Boolean(jobIdParam)}
            />
          ) : null}
          {resultContextSource ? (
            <Typography variant="caption" color="text.secondary">
              Resolved: {resultContextSource}
              {visibleJobId ? ` · job ${visibleJobId.slice(0, 10)}…` : ''}
              {!jobIdParam && visibleJobId && effectiveSelectorJobId === visibleJobId
                ? ' (matches selector — no URL pin)'
                : null}
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

      <Dialog open={compareDialogOpen} onClose={() => setCompareDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Compare two runs (benchmark)</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose two explicit job ids for this aisle. Compare is read-only and does not change the operational
            slice.
          </Typography>
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel id="cmp-a-label">Run A</InputLabel>
            <Select
              labelId="cmp-a-label"
              label="Run A"
              value={compareJobA}
              onChange={(e) => setCompareJobA(String(e.target.value))}
            >
              {jobs.map((j) => (
                <MenuItem key={`a-${j.id}`} value={j.id}>
                  {j.id.slice(0, 10)}… · {j.status}
                  {j.is_operational ? ' · operational' : ''}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth size="small">
            <InputLabel id="cmp-b-label">Run B</InputLabel>
            <Select
              labelId="cmp-b-label"
              label="Run B"
              value={compareJobB}
              onChange={(e) => setCompareJobB(String(e.target.value))}
            >
              {jobs.map((j) => (
                <MenuItem key={`b-${j.id}`} value={j.id}>
                  {j.id.slice(0, 10)}… · {j.status}
                  {j.is_operational ? ' · operational' : ''}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCompareDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!compareJobA || !compareJobB || compareJobA === compareJobB}
            onClick={() => {
              setCompareDialogOpen(false);
              navigate(
                `/inventories/${inventoryId}/aisles/${aisleId}/compare?jobAId=${encodeURIComponent(compareJobA)}&jobBId=${encodeURIComponent(compareJobB)}`
              );
            }}
          >
            Open compare
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={promoteDialogOpen} onClose={() => setPromoteDialogOpen(false)}>
        <DialogTitle>Promote run to operational</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Sets the aisle operational pointer to the selected succeeded job. Other runs stay stored for
            benchmarking; review edits apply only to the operational slice. SKU corrections are not copied from
            other runs automatically.
          </Typography>
          <FormControl fullWidth size="small">
            <InputLabel id="promote-job-label">Job</InputLabel>
            <Select
              labelId="promote-job-label"
              label="Job"
              value={promoteJobId}
              onChange={(e) => setPromoteJobId(String(e.target.value))}
            >
              {jobs
                .filter((j) => j.status === 'succeeded' && j.id !== operationalJobId)
                .map((j) => (
                  <MenuItem key={j.id} value={j.id}>
                    {j.id.slice(0, 12)}… · {j.provider_name ?? '—'} · {j.prompt_key ?? '—'}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPromoteDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={!promoteJobId || promoteMutation.isPending}
            onClick={() => {
              void (async () => {
                try {
                  await promoteMutation.mutateAsync(promoteJobId);
                  setPromoteDialogOpen(false);
                  showSnackbar('Operational run updated', 'success');
                  void refetch();
                  void aisleJobsQuery.refetch();
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(getApiErrorMessage(err, 'Promotion failed'), 'error');
                }
              })();
            }}
          >
            {promoteMutation.isPending ? 'Promoting…' : 'Confirm promote'}
          </Button>
        </DialogActions>
      </Dialog>

      <QuickReviewDrawer
        open={Boolean(quickContext)}
        context={quickContext}
        onClose={() => setQuickContext(null)}
      />
    </>
  );
}
