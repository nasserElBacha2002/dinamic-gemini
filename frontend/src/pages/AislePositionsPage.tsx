/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { exportAisleResultsCsv, getAisleMergeResults, type AislePositionsListQuery } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { canonicalizeOptionalId } from '../api/queryParamCanonicalization';
import { recordExplicitRefreshObs, summarizeQueryKey } from '../dev/cacheMutationObservability';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import type { MergeResultItemResponse, RunMergeResponse } from '../api/types';
import { ApiError } from '../api/types';
import { PageHeader } from '../components/shell';
import { FilterToolbar, SectionCard, TableSearchField, useAppSnackbar } from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { ROUTE_HOME, pathToInventory, pathToInventoryAnalyticsCompare } from '../constants/appRoutes';
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
import PromoteOperationalDialog from '../features/benchmark/PromoteOperationalDialog';

/** List query: photo-grouped order, no SKU merge — matches operator photo-review expectations. */
const AISLE_RESULTS_LIST_QUERY: AislePositionsListQuery = {
  page: 1,
  page_size: 500,
  sort_by: 'photo_sequence',
  sort_dir: 'asc',
  consolidate_by_sku: false,
};

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

function mergeConsolidatedDetail(t: TFunction, summary: MergeResultsSummary): string {
  const examples =
    summary.skuExamples.length > 0
      ? t('positions.merge_examples_paren', { list: summary.skuExamples.join(', ') })
      : '';
  if (summary.groupCount === 1) {
    return t('positions.merge_repeated_sku_one', { examples });
  }
  return t('positions.merge_repeated_sku_other', { count: summary.groupCount, examples });
}

export default function AislePositionsPage() {
  const { t } = useTranslation();
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
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [promoteJobId, setPromoteJobId] = useState('');
  /** `photo` keeps API order; `priority` applies client-side review ranking on top of loaded rows. */
  const [tableSort, setTableSort] = useState<'photo' | 'priority'>('photo');
  const consumedAisleRedirectKey = useRef<string | null>(null);
  const routeIdentityRef = useRef<string>('');
  const queryClient = useQueryClient();
  const mergeMutation = useRunAisleMerge(inventoryId ?? '');
  const promoteMutation = usePromoteAisleOperationalJob(inventoryId ?? '', aisleId ?? '');

  const jobIdParam = searchParams.get('jobId')?.trim() || null;

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
  const isTestInventory = inventory?.processing_mode === 'test';

  /**
   * Concrete run for positions list + URL when jobs exist: valid `?jobId=` if listed, else
   * `operational_job_id` from listAisleJobs when listed, else first job. Operational pointer is API-owned;
   * promote flow updates it — we do not persist a separate “default run” client-side.
   */
  const pickedRunJobId = useMemo(() => {
    if (jobs.length === 0) return null;
    const url = jobIdParam?.trim();
    if (url && jobs.some((j) => j.id === url)) return url;
    if (operationalJobId && jobs.some((j) => j.id === operationalJobId)) return operationalJobId;
    return jobs[0]?.id ?? null;
  }, [jobs, operationalJobId, jobIdParam]);

  const blockPositionsForTestNoJobs = Boolean(
    isTestInventory && aisleJobsQuery.isFetched && !aisleJobsQuery.isLoading && jobs.length === 0
  );
  const positionsQueryEnabled = Boolean(
    inventoryId &&
      aisleId &&
      inventoryQuery.data &&
      aisleJobsQuery.isFetched &&
      !blockPositionsForTestNoJobs
  );

  const positionsListQuery = useMemo<AislePositionsListQuery>(() => {
    const base: AislePositionsListQuery = { ...AISLE_RESULTS_LIST_QUERY };
    if (aisleJobsQuery.isFetched && pickedRunJobId) {
      return { ...base, job_id: pickedRunJobId };
    }
    return base;
  }, [aisleJobsQuery.isFetched, pickedRunJobId]);
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
  } = useResultSummaries(inventoryId, aisleId, {
    listQuery: positionsListQuery,
    enabled: positionsQueryEnabled,
  });
  const positions = positionsFromQuery ?? [];
  const mergeResultsQuery = useAisleMergeResults(inventoryId, aisleId, {
    enabled: Boolean(inventoryId && aisleId && results.length > 0),
    jobId: resultJobId,
  });

  const handleRunSelectionChange = useCallback(
    (next: string) => {
      const trimmed = next.trim();
      if (!trimmed) return;
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.set('jobId', trimmed);
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

  const navigateToAnalyticsCompare = useCallback(() => {
    if (!inventoryId || !aisleId) return;
    if (jobs.length < 2) return;
    const a = visibleJobId ?? jobs[0]?.id ?? '';
    const b = jobs.find((j) => j.id !== a)?.id ?? '';
    if (!a || !b || a === b) return;
    const params = new URLSearchParams();
    params.set('aisleId', aisleId);
    params.set('jobAId', a);
    params.set('jobBId', b);
    navigate(`${pathToInventoryAnalyticsCompare(inventoryId)}?${params.toString()}`);
  }, [aisleId, inventoryId, jobs, navigate, visibleJobId]);

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

  /** Keep URL aligned with the concrete run used for fetching (valid/missing jobId → canonical pick). */
  useEffect(() => {
    if (!inventoryId || !aisleId) return;
    if (!aisleJobsQuery.isFetched) return;
    if (jobs.length === 0 || !pickedRunJobId) return;
    if (jobIdParam === pickedRunJobId) return;
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set('jobId', pickedRunJobId);
        return p;
      },
      { replace: true }
    );
  }, [
    aisleId,
    aisleJobsQuery.isFetched,
    inventoryId,
    jobIdParam,
    jobs.length,
    pickedRunJobId,
    setSearchParams,
  ]);

  const waitingForJobsList = Boolean(inventoryId && aisleId && inventoryQuery.data && !aisleJobsQuery.isFetched);
  const resultsLoading = waitingForJobsList || isLoading;

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

  const sortedForTable = useMemo(
    () => (tableSort === 'priority' ? sortResultsByPriority(filteredBySku) : filteredBySku),
    [filteredBySku, tableSort]
  );

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

  const compareOperationalShortcut =
    Boolean(
      isTestInventory &&
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
        aisleCode: aisle?.code ?? t('common.em_dash'),
        aisleId,
        positionId: resultId,
        resultIds: sortedForTable.map((r) => r.id),
        returnTo: 'aisle_results',
        filter,
        jobId: visibleJobId ?? undefined,
        exactPositionDetail: true,
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
      t,
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
      aisleCode: aisle?.code ?? t('common.em_dash'),
      aisleId,
      positionId: p.positionId,
      resultIds: p.resultIds,
      returnTo: 'aisle_results',
      filter: p.filter ?? filter,
      jobId: p.jobId,
      exactPositionDetail: p.exactPositionDetail ?? true,
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
  ]);

  const handleClearFilterOnly = useCallback(() => setFilter('all'), []);

  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? resolveApiErrorMessage(error, 'errors.load_results')
        : String(error)
      : null;
  const hasResults = !resultsLoading && results.length > 0;
  const mergeCandidates = useMemo(() => summarizeLikelyMergeCandidates(positions), [positions]);
  const mergeResultsSummary = useMemo(
    () => summarizeMergeResults(mergeResultsQuery.data?.results),
    [mergeResultsQuery.data?.results]
  );
  const mergeButtonVisible = Boolean(inventoryId && aisleId && hasResults);
  const mergeButtonDisabled = mergeMutation.isPending || mergeCandidates.groupCount === 0;
  const mergeDisabledReason =
    mergeCandidates.groupCount === 0 ? t('positions.merge_no_skus') : '';
  const mergeFeedback = useMemo(() => {
    if (lastMergeResponse != null) {
      if (lastMergeResponse.product_records_updated > 0) {
        const detailExtra = lastMergeSummary
          ? t('positions.merge_visible_detail_space', { detail: mergeConsolidatedDetail(t, lastMergeSummary) })
          : '';
        return {
          severity: 'success' as const,
          text: `${t('positions.merge_visible_updated')}${detailExtra}`,
        };
      }
      return {
        severity: 'info' as const,
        text: t('positions.merge_no_change'),
      };
    }
    if (mergeResultsSummary != null) {
      return {
        severity: 'info' as const,
        text: t('positions.merge_history_consolidated', {
          detail: mergeConsolidatedDetail(t, mergeResultsSummary),
        }),
      };
    }
    return null;
  }, [lastMergeResponse, lastMergeSummary, mergeResultsSummary, t]);

  const handleRunMerge = useCallback(async () => {
    if (!inventoryId || !aisleId) return;
    try {
      setLastMergeResponse(null);
      setLastMergeSummary(null);
      const result = await mergeMutation.mutateAsync({
        aisleId,
        jobId: visibleJobId ?? null,
      });
      // Single merge-results refresh (mutation only invalidates positions — avoids invalidate+refetch duplicate GET).
      const jobIdCanon = canonicalizeOptionalId(visibleJobId);
      const mergeKey = queryKeys.inventories.mergeResultsForJob(inventoryId, aisleId, jobIdCanon);
      const mergePayload = await queryClient.fetchQuery({
        queryKey: mergeKey,
        queryFn: () => getAisleMergeResults(inventoryId, aisleId, { jobId: jobIdCanon }),
      });
      recordExplicitRefreshObs({
        flow: 'merge_merge_results',
        mechanism: 'fetchQuery',
        keySummary: summarizeQueryKey(mergeKey),
      });
      setLastMergeResponse(result);
      setLastMergeSummary(summarizeMergeResults(mergePayload.results));
      showSnackbar(
        result.product_records_updated > 0 ? t('positions.merge_started') : t('positions.merge_no_change'),
        'success'
      );
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.merge_failed'), 'error');
    }
  }, [aisleId, inventoryId, mergeMutation, queryClient, showSnackbar, t, visibleJobId]);

  if (!inventoryId || !aisleId) {
    return (
      <>
        <Alert severity="warning">{t('positions.missing_inventory_aisle_page')}</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate(ROUTE_HOME)}>
          {t('inventory.back_to_list')}
        </Button>
      </>
    );
  }

  const breadcrumbs = [
    { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
    ...(inventory
      ? [{ label: inventory.name, to: pathToInventory(inventoryId) }]
      : []),
    { label: t('positions.breadcrumb_results') },
  ];

  const positionsLoadNotFound =
    isError && error instanceof ApiError && error.status === 404 && Boolean(jobIdParam);

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={aisle?.code ?? t('common.aisle')}
        subtitle={inventory?.name ?? (inventoryQuery.isLoading ? t('common.loading') : t('common.em_dash'))}
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
                    {mergeMutation.isPending ? t('common.merging') : t('aisle.merge_repeated_labels')}
                  </Button>
                </span>
              </Tooltip>
            ) : null}
            {isTestInventory && jobs.length >= 2 ? (
              <Button size="small" variant="outlined" onClick={navigateToAnalyticsCompare}>
                {t('positions.compare_runs')}
              </Button>
            ) : null}
            {compareOperationalShortcut ? (
              <Tooltip title={t('aisle.compare_runs_tooltip')}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    const params = new URLSearchParams();
                    params.set('aisleId', aisleId!);
                    params.set('jobAId', visibleJobId!);
                    params.set('jobBId', operationalJobId!);
                    navigate(`${pathToInventoryAnalyticsCompare(inventoryId)}?${params.toString()}`);
                  }}
                >
                  {t('positions.compare_to_operational')}
                </Button>
              </Tooltip>
            ) : null}
            {isTestInventory && canPromoteCurrentRun ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  setPromoteJobId(visibleJobId ?? '');
                  setPromoteDialogOpen(true);
                }}
              >
                {t('positions.promote_run')}
              </Button>
            ) : null}
            <Button
              size="small"
              variant="outlined"
              disabled={!inventoryId || !aisleId || exportingCsv}
              onClick={async () => {
                if (!inventoryId || !aisleId) return;
                setExportingCsv(true);
                try {
                  await exportAisleResultsCsv(inventoryId, aisleId, {
                    jobId: pickedRunJobId ?? jobIdParam,
                  });
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
                } finally {
                  setExportingCsv(false);
                }
              }}
            >
              {exportingCsv ? t('common.exporting') : t('positions.export_aisle_csv')}
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                void refetch();
                void aisleJobsQuery.refetch();
              }}
              disabled={resultsLoading}
            >
              {t('common.refresh')}
            </Button>
          </Box>
        }
      />

      {isTestInventory &&
      (aisleJobsQuery.isLoading || jobs.length > 0 || Boolean(resultContextSource)) ? (
        <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          {aisleJobsQuery.isLoading && jobs.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('common.loading')}
            </Typography>
          ) : jobs.length > 0 && pickedRunJobId ? (
            <AisleRunSelector
              operationalJobId={aisleJobsQuery.data?.operational_job_id ?? null}
              jobs={jobs}
              valueJobId={pickedRunJobId}
              onChange={handleRunSelectionChange}
            />
          ) : null}
          {resultContextSource ? (
            <Typography variant="caption" color="text.secondary">
              {t('positions.resolved_line', {
                source: resultContextSource,
                jobSuffix: visibleJobId
                  ? t('positions.resolved_job_bit', { id: `${visibleJobId.slice(0, 10)}…` })
                  : '',
                noPinNote: '',
              })}
            </Typography>
          ) : null}
        </Box>
      ) : null}

      {positionsLoadNotFound ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              disabled={!pickedRunJobId}
              onClick={() => {
                if (pickedRunJobId) handleRunSelectionChange(pickedRunJobId);
              }}
            >
              {t('positions.clear_run_filter')}
            </Button>
          }
        >
          {t('positions.no_data_for_run')}
        </Alert>
      ) : null}

      {errorMessage ? <ResultsErrorState message={errorMessage} onRetry={() => refetch()} /> : null}

      {blockPositionsForTestNoJobs ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('positions.no_runs_for_aisle')}
        </Alert>
      ) : null}

      {!blockPositionsForTestNoJobs && !errorMessage && resultsLoading ? (
        <ResultsLoadingState message={t('positions.loading_results')} />
      ) : null}

      {!blockPositionsForTestNoJobs && !errorMessage && !resultsLoading && results.length === 0 ? (
        <>
          <Box sx={{ mb: 3, mt: 1 }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              {t('positions.counted_total')}
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
              {kpi.aisleTotalCounted}
            </Typography>
          </Box>

          <FilterToolbar
            onReset={handleResetFilters}
            resetDisabled={filter === 'all' && !skuSearch.trim()}
          >
            <TableSearchField
              label={t('positions.search_label')}
              placeholder={t('positions.filter_sku_placeholder')}
              value={skuSearch}
              onChange={(v) => {
                setSkuSearch(v);
                setPage(1);
              }}
              data-testid="aisle-positions-sku-search"
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
          <ResultsEmptyState message={t('positions.empty_results')} />
        </>
      ) : null}

      {!blockPositionsForTestNoJobs && !errorMessage && !resultsLoading && results.length > 0 ? (
        <>
          <Box sx={{ mb: 3, mt: 1 }}>
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 600 }}>
              {t('positions.counted_total')}
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
            <TableSearchField
              label={t('positions.search_label')}
              placeholder={t('positions.filter_sku_placeholder')}
              value={skuSearch}
              onChange={(v) => {
                setSkuSearch(v);
                setPage(1);
              }}
              data-testid="aisle-positions-sku-search"
            />
            <Tooltip title={tableSort === 'photo' ? t('positions.order_api') : t('positions.order_client')}>
              <span>
                <ToggleButtonGroup
                  size="small"
                  exclusive
                  value={tableSort}
                  onChange={(_, value) => {
                    if (value != null) setTableSort(value);
                  }}
                  aria-label={t('common.row_order')}
                >
                  <ToggleButton value="photo">{t('positions.photo_order')}</ToggleButton>
                  <ToggleButton value="priority">{t('positions.review_priority_sort')}</ToggleButton>
                </ToggleButtonGroup>
              </span>
            </Tooltip>
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
            <SectionCard title={t('positions.title_results')}>
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

      {isTestInventory ? (
      <PromoteOperationalDialog
        open={promoteDialogOpen}
        onClose={() => setPromoteDialogOpen(false)}
        jobs={jobs}
        operationalJobId={operationalJobId}
        promoteJobId={promoteJobId}
        onPromoteJobIdChange={setPromoteJobId}
        isPending={promoteMutation.isPending}
        onConfirm={() => {
          void (async () => {
            try {
              await promoteMutation.mutateAsync(promoteJobId);
              setPromoteDialogOpen(false);
              showSnackbar(t('aisle.operational_updated_snackbar'), 'success');
            } catch (e) {
              const err = e instanceof ApiError ? e : new ApiError(String(e));
              showSnackbar(resolveApiErrorMessage(err, 'errors.promotion_failed'), 'error');
            }
          })();
        }}
      />
      ) : null}

      <QuickReviewDrawer
        open={Boolean(quickContext)}
        context={quickContext}
        onClose={() => setQuickContext(null)}
      />
    </>
  );
}
