/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Box, Button, TextField, Typography } from '@mui/material';
import { exportInventoryResultsCsv } from '../api/client';
import { getApiErrorMessage } from '../utils/apiErrors';
import { ApiError } from '../api/types';
import { PageHeader } from '../components/shell';
import { FilterToolbar, SectionCard, useAppSnackbar } from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { useInventoryDetail, useAislesList, useRunAisleMerge } from '../hooks';
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
} from '../features/results/components';

export default function AislePositionsPage() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { showSnackbar } = useAppSnackbar();
  const [filter, setFilter] = useState<ResultsFilterKind>(() =>
    getInitialFilterFromReturnState(location.state)
  );
  const [skuSearch, setSkuSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);
  const [quickContext, setQuickContext] = useState<QuickReviewContext | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const consumedAisleRedirectKey = useRef<string | null>(null);
  const mergeMutation = useRunAisleMerge(inventoryId ?? '');

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const inventory = inventoryQuery.data ?? null;
  const aisle = useMemo(
    () => aislesQuery.data?.items?.find((a) => a.id === aisleId) ?? null,
    [aislesQuery.data?.items, aisleId]
  );

  const { results, positions: positionsFromQuery, isLoading, isError, error, refetch } = useResultSummaries(
    inventoryId,
    aisleId
  );
  const positions = positionsFromQuery ?? [];

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
      return sku.includes(q);
    });
  }, [filteredByKind, skuSearch]);

  const sortedForTable = useMemo(() => sortResultsByPriority(filteredBySku), [filteredBySku]);

  useEffect(() => {
    if (sortedForTable.length === 0) return;
    const pages = Math.max(1, Math.ceil(sortedForTable.length / pageSize));
    if (page > pages) setPage(pages);
  }, [sortedForTable.length, pageSize, page]);

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
      });
    },
    [positionById, inventoryId, inventory, aisle?.code, aisleId, sortedForTable, filter]
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
  const canRunMerge = Boolean(inventoryId && aisleId && !isLoading && results.length > 0);

  const handleRunMerge = useCallback(async () => {
    if (!inventoryId || !aisleId) return;
    try {
      const result = await mergeMutation.mutateAsync(aisleId);
      await Promise.all([refetch(), aislesQuery.refetch()]);
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
  }, [aisleId, aislesQuery, inventoryId, mergeMutation, refetch, showSnackbar]);

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

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={aisle?.code ?? 'Aisle'}
        subtitle={inventory?.name ?? (inventoryQuery.isLoading ? 'Loading…' : '—')}
        actions={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
            {canRunMerge ? (
              <Button
                size="small"
                variant="contained"
                onClick={() => void handleRunMerge()}
                disabled={mergeMutation.isPending}
              >
                {mergeMutation.isPending ? 'Merging…' : 'Merge repeated labels'}
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
            <Button size="small" variant="outlined" onClick={() => refetch()} disabled={isLoading}>
              Refresh
            </Button>
          </Box>
        }
      />

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
              label="Search SKU"
              placeholder="Filter by SKU"
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

          <FilterToolbar
            onReset={handleResetFilters}
            resetDisabled={filter === 'all' && !skuSearch.trim()}
          >
            <TextField
              size="small"
              label="Search SKU"
              placeholder="Filter by SKU"
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
