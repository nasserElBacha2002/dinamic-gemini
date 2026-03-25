/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Alert, Box, Button, TextField } from '@mui/material';
import { pathToPositionDetail } from '../utils/resultRoutes';
import { getApiErrorMessage } from '../utils/apiErrors';
import { ApiError } from '../api/types';
import { PageHeader } from '../components/shell';
import { FilterToolbar, SectionCard } from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { useInventoryDetail, useAislesList } from '../hooks';
import {
  useResultSummaries,
  computeResultsKpi,
  filterResults,
  sortResultsByPriority,
  getInitialFilterFromReturnState,
  type ResultDetailNavigationState,
  type ResultsFilterKind,
} from '../features/results';
import {
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
  const [skuSearch, setSkuSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const inventory = inventoryQuery.data ?? null;
  const aisle = useMemo(
    () => aislesQuery.data?.items?.find((a) => a.id === aisleId) ?? null,
    [aislesQuery.data?.items, aisleId]
  );

  const { results, isLoading, isError, error, refetch } = useResultSummaries(inventoryId, aisleId);

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

  const handleOpenDetail = useCallback(
    (resultId: string) => {
      if (inventoryId && aisleId) {
        const navigationState: ResultDetailNavigationState = {
          resultIds: sortedForTable.map((r) => r.id),
          filter,
        };
        navigate(pathToPositionDetail(inventoryId, aisleId, resultId), {
          state: navigationState,
        });
      }
    },
    [navigate, inventoryId, aisleId, sortedForTable, filter]
  );

  const handleClearFilterOnly = useCallback(() => setFilter('all'), []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load results')
        : String(error)
      : null;

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
          <Button size="small" variant="outlined" onClick={() => refetch()} disabled={isLoading}>
            Refresh
          </Button>
        }
      />

      {errorMessage ? <ResultsErrorState message={errorMessage} onRetry={() => refetch()} /> : null}

      {!errorMessage && isLoading ? <ResultsLoadingState message="Loading results…" /> : null}

      {!errorMessage && !isLoading && results.length === 0 ? (
        <>
          <ResultsKpiCards kpi={kpi} />
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
          <ResultsKpiCards kpi={kpi} />

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
                  onOpenDetail={handleOpenDetail}
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
    </>
  );
}
