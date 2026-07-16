/**
 * Sprint 4.1 — Aisle Results: review prioritization for one aisle (header → KPIs → filters → table → pagination).
 */

import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, Tooltip, Typography } from '@mui/material';
import PhotoLibraryOutlinedIcon from '@mui/icons-material/PhotoLibraryOutlined';
import ImageSearchOutlinedIcon from '@mui/icons-material/ImageSearchOutlined';
import { exportAisleOperationalCsv, getAisleMergeResults, type AislePositionsListQuery } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { canonicalizeOptionalId } from '../api/queryParamCanonicalization';
import { recordExplicitRefreshObs, summarizeQueryKey } from '../dev/cacheMutationObservability';
import { getVisibleErrorMessage, resolveApiErrorMessage } from '../utils/apiErrors';
import { isAisleActive } from '../utils/aisleActive';
import type { RunMergeResponse } from '../api/types';
import { ApiError } from '../api/types';
import {
  ConfirmDialog,
  FilterToolbar,
  TableSearchField,
  sortDataTableRows,
  useAppSnackbar,
  useErrorSnackbar,
  type DataTableSortDirection,
} from '../components/ui';
import { TABLE_SERVER_SEARCH_DEBOUNCE_MS } from '../constants/dataTable';
import {
  ROUTE_HOME,
  pathToAisleObservability,
  pathToInventory,
  pathToInventoryAnalyticsCompareMany,
} from '../constants/appRoutes';
import {
  useInventoryDetail,
  useAislesList,
  useAisleMergeResults,
  useRunAisleMerge,
  useAisleJobsList,
  useJobImageResults,
  usePromoteAisleOperationalJob,
  useUpdateAisle,
  useDeactivateAisle,
  useActivateAisle,
} from '../hooks';
import EditAisleCodeDialog from '../features/inventories/components/EditAisleCodeDialog';
import {
  useResultSummaries,
  computeResultsKpi,
  filterResults,
  sortResultsByPriority,
  getInitialFilterFromReturnState,
} from '../features/results';
import {
  aisleResultsSearchParamsEqual,
  areAisleResultsFiltersEqual,
  createDefaultAisleResultsFilters,
  isAisleResultsSortColumn,
  mergeAisleResultsFilterPatch,
  parseAisleResultsFilters,
  writeAisleResultsFilters,
  type AisleResultsUrlFilters,
} from '../features/results/utils/aisleResultsUrlFilters';
import QuickReviewDrawer from '../features/reviewQueue/components/QuickReviewDrawer';
import type { OpenReviewDrawerPayload, QuickReviewContext } from '../features/reviewQueue/quickReviewContext';
import {
  ResultsQuickFilters,
  ResultsEmptyState,
  ResultsLoadingState,
  ResultsErrorState,
  AisleResultsJobSelector,
  AisleResultsRunNotFoundAlert,
  AisleResultsNoJobsAlert,
  AisleResultsHeader,
  AisleResultsTableSection,
  JobImageResultsViewToggle,
  JobImageResultsGrid,
  ManualImageResultDrawer,
} from '../features/results/components';
import type { JobImageResultItem } from '../api/types';
import { buildResultsTableColumns } from '../features/results/components/resultsTableColumns';
import { mergeConsolidatedDetail } from '../features/results/adapters/aislePositionsFormatters';
import {
  summarizeLikelyMergeCandidates,
  summarizeMergeResults,
  type MergeResultsSummary,
} from '../features/results/adapters/aislePositionsViewModel';
import PromoteOperationalDialog from '../features/benchmark/PromoteOperationalDialog';
import AisleSourceAssetsManageModule from '../features/inventories/components/AisleSourceAssetsManageModule';
import AisleVisualReferencesModule from '../features/inventories/components/AisleVisualReferencesModule';
import CodeScanDrawer from '../features/aisle-code-scans/components/CodeScanDrawer';

/** List query: photo-grouped order, no SKU merge — matches operator photo-review expectations. */
const AISLE_RESULTS_LIST_QUERY: AislePositionsListQuery = {
  page: 1,
  page_size: 500,
  sort_by: 'photo_sequence',
  sort_dir: 'asc',
  consolidate_by_sku: false,
};

export default function AislePositionsPage() {
  const { t } = useTranslation();
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { showSnackbar } = useAppSnackbar();
  const { showErrorSnackbar } = useErrorSnackbar();
  const filterDefaults = useMemo(() => createDefaultAisleResultsFilters(), []);
  const urlFilters = useMemo(
    () => parseAisleResultsFilters(searchParams, filterDefaults),
    [searchParams, filterDefaults]
  );
  const filter = urlFilters.filter;
  const page = urlFilters.page;
  const pageSize = urlFilters.pageSize;
  const tableSort = urlFilters.tableSort;
  const resultsColumnSortBy = urlFilters.sortBy ?? '';
  const resultsColumnSortDir = urlFilters.sortDir;
  const resultsView = urlFilters.resultsView;
  const [searchDraft, setSearchDraft] = useState(() => urlFilters.q);
  const [quickContext, setQuickContext] = useState<QuickReviewContext | null>(null);
  const [manualResultItem, setManualResultItem] = useState<JobImageResultItem | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [lastMergeResponse, setLastMergeResponse] = useState<RunMergeResponse | null>(null);
  const [lastMergeSummary, setLastMergeSummary] = useState<MergeResultsSummary | null>(null);
  const [lastMergeContextKey, setLastMergeContextKey] = useState<string | null>(null);
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [codeScanDrawerOpen, setCodeScanDrawerOpen] = useState(false);
  const [editCodeOpen, setEditCodeOpen] = useState(false);
  const [deactivateConfirmOpen, setDeactivateConfirmOpen] = useState(false);
  const [reactivateConfirmOpen, setReactivateConfirmOpen] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [promoteJobId, setPromoteJobId] = useState('');
  const consumedAisleRedirectKey = useRef<string | null>(null);
  const routeIdentityRef = useRef<string>('');
  const legacyFilterHydratedRef = useRef(false);
  const queryClient = useQueryClient();
  const mergeMutation = useRunAisleMerge(inventoryId ?? '');
  const promoteMutation = usePromoteAisleOperationalJob(inventoryId ?? '', aisleId ?? '');
  const updateAisleMutation = useUpdateAisle(inventoryId ?? '');
  const deactivateAisleMutation = useDeactivateAisle(inventoryId ?? '');
  const activateAisleMutation = useActivateAisle(inventoryId ?? '');

  const jobIdParam = searchParams.get('jobId')?.trim() || null;

  const updateFilters = useCallback(
    (
      patch: Partial<AisleResultsUrlFilters>,
      options?: {
        resetPage?: boolean;
        historyMode?: 'push' | 'replace';
        clampPageTo?: number;
      }
    ) => {
      setSearchParams(
        (prev) => {
          const current = parseAisleResultsFilters(prev, filterDefaults);
          const merged = mergeAisleResultsFilterPatch(current, patch, {
            resetPage: options?.resetPage,
            clampPageTo: options?.clampPageTo,
          });
          const next = writeAisleResultsFilters(prev, merged, filterDefaults);
          if (aisleResultsSearchParamsEqual(prev, next)) return prev;
          return next;
        },
        { replace: options?.historyMode === 'replace' }
      );
    },
    [filterDefaults, setSearchParams]
  );

  /** Sync search input when URL changes (back/forward / shared link). */
  useEffect(() => {
    setSearchDraft(urlFilters.q);
  }, [urlFilters.q]);

  /** Debounce search draft → URL (`replace`). Empty clears immediately. */
  useEffect(() => {
    const trimmed = searchDraft.trim();
    if (trimmed === urlFilters.q) return;
    if (trimmed === '') {
      updateFilters({ q: '' }, { resetPage: true, historyMode: 'replace' });
      return;
    }
    const id = window.setTimeout(() => {
      updateFilters({ q: trimmed }, { resetPage: true, historyMode: 'replace' });
    }, TABLE_SERVER_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [searchDraft, urlFilters.q, updateFilters]);

  /** Legacy `location.state.filter` when URL has no explicit filter key. */
  useEffect(() => {
    if (legacyFilterHydratedRef.current) return;
    legacyFilterHydratedRef.current = true;
    if (searchParams.has('filter')) return;
    const fromState = getInitialFilterFromReturnState(location.state);
    if (fromState === 'all') return;
    updateFilters({ filter: fromState }, { historyMode: 'replace' });
  }, [location.state, searchParams, updateFilters]);

  /** Canonize invalid / default-equivalent filter params with replace (preserve jobId). */
  useEffect(() => {
    const canonical = writeAisleResultsFilters(searchParams, urlFilters, filterDefaults);
    if (aisleResultsSearchParamsEqual(searchParams, canonical)) return;
    setSearchParams(canonical, { replace: true });
  }, [searchParams, urlFilters, filterDefaults, setSearchParams]);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const aisleJobsQuery = useAisleJobsList(inventoryId, aisleId, {
    enabled: Boolean(inventoryId && aisleId && inventoryQuery.data),
  });
  const jobs = useMemo(() => aisleJobsQuery.data?.jobs ?? [], [aisleJobsQuery.data?.jobs]);
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
  const aisleIsActive = isAisleActive(aisle);
  const otherAisleCodes = useMemo(
    () =>
      (aislesQuery.data?.items ?? [])
        .filter((a) => a.id !== aisleId)
        .map((a) => a.code),
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
  const positions = useMemo(() => positionsFromQuery ?? [], [positionsFromQuery]);
  const mergeResultsQuery = useAisleMergeResults(inventoryId, aisleId, {
    enabled: Boolean(inventoryId && aisleId && results.length > 0),
    jobId: resultJobId,
  });

  /** Lightweight counters only — enables/disables the unmatched-images tab without loading the queue. */
  const unmatchedCountersQuery = useJobImageResults(
    inventoryId,
    aisleId,
    pickedRunJobId ?? undefined,
    { result_status: 'without_result', page: 1, page_size: 1 },
    { enabled: Boolean(pickedRunJobId) }
  );
  /** Full unmatched queue — deferred until the images view is active. */
  const imageResultsQuery = useJobImageResults(
    inventoryId,
    aisleId,
    pickedRunJobId ?? undefined,
    {
      result_status: 'without_result',
      page,
      page_size: pageSize,
    },
    { enabled: resultsView === 'images' && Boolean(pickedRunJobId) }
  );
  const imageResultsItems = imageResultsQuery.data?.items ?? [];
  const withoutResultCount =
    imageResultsQuery.data?.counters?.without_result ??
    unmatchedCountersQuery.data?.counters?.without_result ??
    0;
  const unmatchedCountersReady =
    unmatchedCountersQuery.isFetched || imageResultsQuery.isFetched;
  const imagesTabDisabled = !unmatchedCountersReady || withoutResultCount === 0;
  const imageResultsErrorMessage = imageResultsQuery.isError
    ? getVisibleErrorMessage(imageResultsQuery.error, 'results')
    : null;

  /** URL `view=images` with zero pending → normalize to positions (replace, no history entry). */
  useEffect(() => {
    if (resultsView !== 'images') return;
    if (!pickedRunJobId) return;
    if (!unmatchedCountersReady) return;
    if (withoutResultCount > 0) return;
    updateFilters({ resultsView: 'positions' }, { historyMode: 'replace' });
  }, [
    resultsView,
    pickedRunJobId,
    unmatchedCountersReady,
    withoutResultCount,
    updateFilters,
  ]);

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
    params.set('jobIds', `${a},${b}`);
    params.set('baseline', a);
    navigate(`${pathToInventoryAnalyticsCompareMany(inventoryId)}?${params.toString()}`);
  }, [aisleId, inventoryId, jobs, navigate, visibleJobId]);

  useEffect(() => {
    const key = `${inventoryId ?? ''}-${aisleId ?? ''}`;
    if (!inventoryId || !aisleId) return;
    if (routeIdentityRef.current !== '' && routeIdentityRef.current !== key) {
      setSearchParams(
        (prev) => {
          if (!prev.has('jobId')) return prev;
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
    const q = urlFilters.q.trim().toLowerCase();
    if (!q) return filteredByKind;
    return filteredByKind.filter((r) => {
      const sku = (r.sku ?? '').trim().toLowerCase();
      const posCode = (r.positionCode ?? '').trim().toLowerCase();
      return sku.includes(q) || posCode.includes(q);
    });
  }, [filteredByKind, urlFilters.q]);

  const sortedForTable = useMemo(
    () => (tableSort === 'priority' ? sortResultsByPriority(filteredBySku) : filteredBySku),
    [filteredBySku, tableSort]
  );

  const resultsSortColumns = useMemo(
    () =>
      buildResultsTableColumns({
        t,
        dash: t('common.em_dash'),
        onOpenReview: () => {},
      }),
    [t]
  );

  const rowsOrderedForTable = useMemo(
    () =>
      !resultsColumnSortBy.trim()
        ? sortedForTable
        : sortDataTableRows(
            sortedForTable,
            resultsSortColumns,
            resultsColumnSortBy,
            resultsColumnSortDir
          ),
    [sortedForTable, resultsSortColumns, resultsColumnSortBy, resultsColumnSortDir]
  );

  const maxPage = Math.max(1, Math.ceil(Math.max(rowsOrderedForTable.length, 1) / pageSize));
  const effectivePage = Math.min(page, maxPage);
  const mergeContextKey = `${inventoryId ?? ''}|${aisleId ?? ''}|${jobIdParam ?? ''}`;
  const mergeFeedbackIsCurrentContext = lastMergeContextKey === mergeContextKey;

  const tableRows = useMemo(() => {
    const start = (effectivePage - 1) * pageSize;
    return rowsOrderedForTable.slice(start, start + pageSize);
  }, [rowsOrderedForTable, effectivePage, pageSize]);

  const handleResultsColumnSortChange = useCallback(
    (sortBy: string, sortDir: DataTableSortDirection) => {
      if (!isAisleResultsSortColumn(sortBy)) return;
      updateFilters(
        { sortBy, sortDir },
        { resetPage: true, historyMode: 'push' }
      );
    },
    [updateFilters]
  );

  const handleResetFilters = useCallback(() => {
    setSearchDraft('');
    updateFilters(createDefaultAisleResultsFilters(), { historyMode: 'push' });
  }, [updateFilters]);

  const prevTableSortRunRef = useRef<{ tableSort: string; run: string | null } | null>(null);
  useEffect(() => {
    const prev = prevTableSortRunRef.current;
    prevTableSortRunRef.current = { tableSort, run: pickedRunJobId };
    if (prev == null) return;
    if (prev.tableSort === tableSort && prev.run === pickedRunJobId) return;
    if (!urlFilters.sortBy) return;
    updateFilters({ sortBy: null }, { historyMode: 'replace' });
  }, [tableSort, pickedRunJobId, urlFilters.sortBy, updateFilters]);

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
        resultIds: rowsOrderedForTable.map((r) => r.id),
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
      rowsOrderedForTable,
      filter,
      visibleJobId,
      t,
    ]
  );

  useEffect(() => {
    const raw = location.state as { openReviewDrawer?: OpenReviewDrawerPayload } | null;
    const p = raw?.openReviewDrawer;
    if (!p || p.kind !== 'aisle' || !inventoryId || !aisleId || !inventory) return;
    if (!p.positionId?.trim() || !Array.isArray(p.resultIds) || p.resultIds.length === 0) return;
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
    // Strip one-shot drawer payload from history; preserve query string (e.g. jobId) on this route.
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: {} });
  }, [
    location.state,
    location.pathname,
    location.search,
    inventory,
    inventoryId,
    aisleId,
    aisle,
    filter,
    navigate,
    t,
  ]);

  const handleClearFilterOnly = useCallback(() => {
    updateFilters({ filter: 'all' }, { resetPage: true, historyMode: 'push' });
  }, [updateFilters]);

  const filtersAtDefault =
    areAisleResultsFiltersEqual(urlFilters, filterDefaults) && searchDraft.trim() === '';

  /** Clamp out-of-range page once results are available. */
  useEffect(() => {
    if (resultsLoading) return;
    if (page <= maxPage) return;
    updateFilters({ page: maxPage }, { historyMode: 'replace' });
  }, [resultsLoading, page, maxPage, updateFilters]);

  const errorMessage =
    isError && error
      ? getVisibleErrorMessage(error, 'results')
      : null;
  const hasResults = !resultsLoading && results.length > 0;
  const mergeCandidates = useMemo(() => summarizeLikelyMergeCandidates(positions), [positions]);
  const mergeResultsSummary = useMemo(
    () => summarizeMergeResults(mergeResultsQuery.data?.results),
    [mergeResultsQuery.data?.results]
  );
  const mergeButtonVisible = Boolean(inventoryId && aisleId && hasResults);
  const mergeButtonDisabled =
    mergeMutation.isPending || mergeCandidates.groupCount === 0 || !aisleIsActive;
  const mergeDisabledReason = !aisleIsActive
    ? t('aisle.operations_disabled_inactive')
    : mergeCandidates.groupCount === 0
      ? t('positions.merge_no_skus')
      : '';
  const mergeFeedback = useMemo(() => {
    if (lastMergeResponse != null && mergeFeedbackIsCurrentContext) {
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
  }, [lastMergeResponse, lastMergeSummary, mergeResultsSummary, t, mergeFeedbackIsCurrentContext]);

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
      setLastMergeContextKey(mergeContextKey);
      showSnackbar(
        result.product_records_updated > 0 ? t('positions.merge_started') : t('positions.merge_no_change'),
        'success'
      );
    } catch (e) {
      showErrorSnackbar(e, 'results');
    }
  }, [aisleId, inventoryId, mergeContextKey, mergeMutation, queryClient, showErrorSnackbar, showSnackbar, t, visibleJobId]);

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

  const inventoryLabel =
    inventory?.name?.trim() ||
    (inventoryQuery.isLoading ? t('common.loading') : t('common.em_dash'));
  const aisleLabel = aisle?.code ?? t('common.aisle');
  const breadcrumbs = [{ label: inventoryLabel, to: pathToInventory(inventoryId) }];

  const positionsLoadNotFound =
    isError && error instanceof ApiError && error.status === 404 && Boolean(jobIdParam);

  return (
    <>
      <CodeScanDrawer
        open={codeScanDrawerOpen}
        onClose={() => setCodeScanDrawerOpen(false)}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobIdForPreview={pickedRunJobId}
        jobIdForMatching={pickedRunJobId}
      />
      <AisleResultsHeader
        breadcrumbs={breadcrumbs}
        title={aisleLabel}
        subtitle=""
        showInactiveBadge={!aisleIsActive}
        onOpenCodeScan={() => setCodeScanDrawerOpen(true)}
        codeScanDisabled={!aisleIsActive}
        onEditName={() => setEditCodeOpen(true)}
        onDeactivate={aisleIsActive ? () => { setLifecycleError(null); setDeactivateConfirmOpen(true); } : undefined}
        onReactivate={!aisleIsActive ? () => { setLifecycleError(null); setReactivateConfirmOpen(true); } : undefined}
        onOpenObservability={
          inventoryId && aisleId
            ? () =>
                navigate(
                  pathToAisleObservability(
                    inventoryId,
                    aisleId,
                    pickedRunJobId ?? visibleJobId
                  )
                )
            : undefined
        }
        assetsAction={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
            <AisleSourceAssetsManageModule
              inventoryId={inventoryId}
              aisleId={aisleId}
              inventoryLabel={inventory?.name ?? t('common.em_dash')}
              jobIdForPreview={pickedRunJobId}
              inventoryReady={Boolean(inventoryQuery.data)}
              readOnly={!aisleIsActive}
            >
              {({ openSourceAssets }) => (
                <Tooltip
                  title={
                    !aisleIsActive
                      ? t('aisle.operations_disabled_inactive')
                      : t('aisle_source_assets.action_tooltip')
                  }
                >
                  <span>
                    <Button
                      data-testid="aisle-source-assets-manage-open"
                      size="small"
                      variant="outlined"
                      startIcon={<PhotoLibraryOutlinedIcon fontSize="small" />}
                      onClick={openSourceAssets}
                      disabled={!aisleIsActive}
                    >
                      {t('aisle_source_assets.action_label')}
                    </Button>
                  </span>
                </Tooltip>
              )}
            </AisleSourceAssetsManageModule>
            <AisleVisualReferencesModule
              inventoryLabel={inventory?.name ?? t('common.em_dash')}
              clientId={inventory?.client_id}
              clientSupplierId={aisle?.client_supplier_id}
              aisle={aisle}
              inventoryReady={Boolean(inventoryQuery.data)}
            >
              {({ openVisualReferences, disabled, disabledTooltip }) => (
                <Tooltip title={disabledTooltip ?? ''} disableHoverListener={!disabledTooltip}>
                  <span>
                    <Button
                      data-testid="aisle-visual-references-open"
                      size="small"
                      variant="outlined"
                      startIcon={<ImageSearchOutlinedIcon fontSize="small" />}
                      onClick={openVisualReferences}
                      disabled={disabled}
                    >
                      {t('positions.visual_references.action_label')}
                    </Button>
                  </span>
                </Tooltip>
              )}
            </AisleVisualReferencesModule>
          </Box>
        }
        mergeButtonVisible={mergeButtonVisible}
        mergeDisabledReason={mergeDisabledReason}
        mergeButtonDisabled={mergeButtonDisabled}
        isMerging={mergeMutation.isPending}
        onRunMerge={() => void handleRunMerge()}
        showCompareRuns={Boolean(isTestInventory && jobs.length >= 2)}
        onCompareRuns={navigateToAnalyticsCompare}
        showCompareOperational={compareOperationalShortcut}
        onCompareOperational={() => {
          const params = new URLSearchParams();
          params.set('aisleId', aisleId!);
          params.set('jobIds', `${visibleJobId!},${operationalJobId!}`);
          params.set('baseline', visibleJobId!);
          navigate(`${pathToInventoryAnalyticsCompareMany(inventoryId!)}?${params.toString()}`);
        }}
        showPromoteRun={Boolean(isTestInventory && canPromoteCurrentRun && aisleIsActive)}
        onPromoteRun={() => {
          setPromoteJobId(visibleJobId ?? '');
          setPromoteDialogOpen(true);
        }}
        exportDisabled={!inventoryId || !aisleId || exportingCsv}
        exportingCsv={exportingCsv}
        onExport={() => {
          void (async () => {
            if (!inventoryId || !aisleId) return;
            setExportingCsv(true);
            try {
              await exportAisleOperationalCsv(inventoryId, aisleId, {
                jobId: pickedRunJobId ?? jobIdParam,
              });
            } catch (e) {
              showErrorSnackbar(e, 'results');
            } finally {
              setExportingCsv(false);
            }
          })();
        }}
        refreshDisabled={resultsLoading}
        onRefresh={() => {
          void refetch();
          void aisleJobsQuery.refetch();
        }}
      />

      {!aisleIsActive ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="aisle-inactive-historical-note">
          {t('aisle.inactive_historical_note')}
        </Alert>
      ) : null}

      <AisleResultsJobSelector
        visible={Boolean(isTestInventory && (aisleJobsQuery.isLoading || jobs.length > 0 || Boolean(resultContextSource)))}
        isJobsLoading={aisleJobsQuery.isLoading}
        jobs={jobs}
        pickedRunJobId={pickedRunJobId}
        operationalJobId={aisleJobsQuery.data?.operational_job_id ?? null}
        resultContextSource={resultContextSource}
        visibleJobId={visibleJobId}
        onRunSelectionChange={handleRunSelectionChange}
      />

      <AisleResultsRunNotFoundAlert
        visible={positionsLoadNotFound}
        canClear={Boolean(pickedRunJobId)}
        onClear={() => {
          if (pickedRunJobId) handleRunSelectionChange(pickedRunJobId);
        }}
      />

      {pickedRunJobId ? (
        <Box sx={{ mb: 2 }}>
          <JobImageResultsViewToggle
            value={resultsView}
            withoutResultCount={withoutResultCount}
            imagesDisabled={imagesTabDisabled}
            onChange={(v) => {
              updateFilters({ resultsView: v }, { historyMode: 'push' });
            }}
          />
        </Box>
      ) : null}

      {resultsView === 'images' && pickedRunJobId ? (
        <JobImageResultsGrid
          items={imageResultsItems}
          isLoading={imageResultsQuery.isLoading}
          errorMessage={imageResultsErrorMessage}
          onRetry={() => void imageResultsQuery.refetch()}
          onAddResult={(item) => setManualResultItem(item)}
          addResultPendingAssetId={manualResultItem?.source_asset_id ?? null}
          page={page}
          pageSize={pageSize}
          totalItems={imageResultsQuery.data?.total_items ?? 0}
          pendingCount={withoutResultCount}
          onPageChange={(nextPage) => {
            updateFilters({ page: nextPage }, { historyMode: 'push' });
          }}
          onPageSizeChange={(nextSize) => {
            updateFilters({ pageSize: nextSize }, { resetPage: true, historyMode: 'push' });
          }}
          onBackToPositions={() => {
            updateFilters({ resultsView: 'positions' }, { historyMode: 'replace' });
          }}
        />
      ) : null}

      {resultsView === 'positions' ? (
        <>
      {errorMessage ? <ResultsErrorState message={errorMessage} onRetry={() => refetch()} /> : null}

      <AisleResultsNoJobsAlert visible={blockPositionsForTestNoJobs} />

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
            <Typography
              variant="body2"
              component="div"
              sx={{ color: 'text.secondary', mt: 0.75, mb: 2, lineHeight: 1.4 }}
            >
              {t('positions.counted_items', { count: kpi.countableResults })}
            </Typography>
          </Box>

          <FilterToolbar
            primary={
              <TableSearchField
                label={t('positions.search_label')}
                placeholder={t('positions.filter_sku_placeholder')}
                value={searchDraft}
                onChange={setSearchDraft}
                data-testid="aisle-positions-sku-search"
              />
            }
            filters={
              <ResultsQuickFilters
                value={filter}
                onChange={(v) => {
                  updateFilters({ filter: v }, { resetPage: true, historyMode: 'push' });
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
            }
            onReset={handleResetFilters}
            resetDisabled={filtersAtDefault}
            activeFilterCount={filter !== 'all' ? 1 : 0}
          />
          <ResultsEmptyState message={t('positions.empty_results')} />
        </>
      ) : null}

      {!blockPositionsForTestNoJobs && !errorMessage && !resultsLoading && results.length > 0 ? (
        <AisleResultsTableSection
          countedTotal={kpi.aisleTotalCounted}
          countedResultRows={kpi.countableResults}
          mergeFeedback={mergeFeedback}
          onResetFilters={handleResetFilters}
          resetDisabled={filtersAtDefault}
          skuSearch={searchDraft}
          onSkuSearchChange={setSearchDraft}
          tableSort={tableSort}
          onTableSortChange={(value) => {
            updateFilters({ tableSort: value }, { resetPage: true, historyMode: 'push' });
          }}
          filter={filter}
          onFilterChange={(v) => {
            updateFilters({ filter: v }, { resetPage: true, historyMode: 'push' });
          }}
          counts={{
            all: kpi.total,
            needs_review: kpi.needsReview,
            low_confidence: kpi.lowConfidence,
            qty_zero: kpi.qtyZero,
            invalid_traceability: kpi.invalidTraceability,
            missing_evidence: missingEvidenceCount,
          }}
          sortedForTableLength={rowsOrderedForTable.length}
          onClearFilterOnly={handleClearFilterOnly}
          tableRows={tableRows}
          onOpenReview={handleOpenReview}
          page={effectivePage}
          pageSize={pageSize}
          totalItems={rowsOrderedForTable.length}
          onPageChange={(nextPage) => {
            updateFilters({ page: nextPage }, { historyMode: 'push' });
          }}
          onPageSizeChange={(nextSize) => {
            updateFilters({ pageSize: nextSize }, { resetPage: true, historyMode: 'push' });
          }}
          columnSort={{
            sortBy: resultsColumnSortBy,
            sortDir: resultsColumnSortDir,
            onSortChange: handleResultsColumnSortChange,
          }}
        />
      ) : null}
        </>
      ) : null}

      <ManualImageResultDrawer
        open={Boolean(manualResultItem)}
        item={manualResultItem}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobId={pickedRunJobId ?? ''}
        onClose={() => setManualResultItem(null)}
        onSuccess={() => {
          setManualResultItem(null);
          // Do not decide tab switch via count-1; the counters effect normalizes to positions.
          void unmatchedCountersQuery.refetch();
          void imageResultsQuery.refetch();
          void refetch();
        }}
        onConflict={() => {
          void unmatchedCountersQuery.refetch();
          void imageResultsQuery.refetch();
        }}
      />

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
              showErrorSnackbar(e, 'results');
            }
          })();
        }}
      />
      ) : null}

      <QuickReviewDrawer
        open={Boolean(quickContext)}
        context={quickContext}
        onClose={() => setQuickContext(null)}
        onOpenCodeScan={() => setCodeScanDrawerOpen(true)}
      />

      <EditAisleCodeDialog
        open={editCodeOpen}
        currentCode={aisle?.code ?? ''}
        existingCodes={otherAisleCodes}
        onClose={() => setEditCodeOpen(false)}
        onSuccess={() => showSnackbar(t('aisle.name_updated_snackbar'), 'success')}
        updateAisleFn={(body) => updateAisleMutation.mutateAsync({ aisleId: aisleId!, body })}
      />

      <ConfirmDialog
        open={deactivateConfirmOpen}
        onClose={() => {
          if (deactivateAisleMutation.isPending) return;
          setDeactivateConfirmOpen(false);
          setLifecycleError(null);
        }}
        title={t('aisle.deactivate_title')}
        description={
          <>
            <strong>{aisle?.code}</strong>
            <br />
            {t('aisle.deactivate_body')}
          </>
        }
        confirmLabel={t('aisle.deactivate_confirm')}
        confirmColor="warning"
        loading={deactivateAisleMutation.isPending}
        errorMessage={lifecycleError}
        onConfirm={() => {
          void (async () => {
            setLifecycleError(null);
            try {
              await deactivateAisleMutation.mutateAsync(aisleId!);
              setDeactivateConfirmOpen(false);
              showSnackbar(t('aisle.deactivate_success_snackbar'), 'success');
            } catch (e) {
              setLifecycleError(
                resolveApiErrorMessage(e, 'errors.aisle_deactivate_active_job')
              );
            }
          })();
        }}
      />

      <ConfirmDialog
        open={reactivateConfirmOpen}
        onClose={() => {
          if (activateAisleMutation.isPending) return;
          setReactivateConfirmOpen(false);
          setLifecycleError(null);
        }}
        title={t('aisle.reactivate_title')}
        description={t('aisle.reactivate_body')}
        confirmLabel={t('aisle.reactivate_confirm')}
        loading={activateAisleMutation.isPending}
        errorMessage={lifecycleError}
        onConfirm={() => {
          void (async () => {
            setLifecycleError(null);
            try {
              await activateAisleMutation.mutateAsync(aisleId!);
              setReactivateConfirmOpen(false);
              showSnackbar(t('aisle.reactivate_success_snackbar'), 'success');
            } catch (e) {
              setLifecycleError(resolveApiErrorMessage(e, 'errors.request_failed'));
            }
          })();
        }}
      />
    </>
  );
}
