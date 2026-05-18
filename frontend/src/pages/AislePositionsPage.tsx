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
import { getVisibleErrorMessage } from '../utils/apiErrors';
import type { RunMergeResponse } from '../api/types';
import { ApiError } from '../api/types';
import {
  FilterToolbar,
  TableSearchField,
  sortDataTableRows,
  useAppSnackbar,
  useErrorSnackbar,
  type DataTableSortDirection,
} from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import {
  ROUTE_HOME,
  pathToInventory,
  pathToInventoryAnalyticsCompareMany,
} from '../constants/appRoutes';
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
  ResultsEmptyState,
  ResultsLoadingState,
  ResultsErrorState,
  AisleResultsJobSelector,
  AisleResultsRunNotFoundAlert,
  AisleResultsNoJobsAlert,
  AisleResultsHeader,
  AisleResultsTableSection,
} from '../features/results/components';
import { buildResultsTableColumns } from '../features/results/components/ResultsTable';
import { mergeConsolidatedDetail } from '../features/results/adapters/aislePositionsFormatters';
import {
  summarizeLikelyMergeCandidates,
  summarizeMergeResults,
  type MergeResultsSummary,
} from '../features/results/adapters/aislePositionsViewModel';
import PromoteOperationalDialog from '../features/benchmark/PromoteOperationalDialog';
import AisleSourceAssetsManageModule from '../features/inventories/components/AisleSourceAssetsManageModule';
import AisleVisualReferencesModule from '../features/inventories/components/AisleVisualReferencesModule';

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
  const [lastMergeContextKey, setLastMergeContextKey] = useState<string | null>(null);
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [promoteJobId, setPromoteJobId] = useState('');
  /** `photo` keeps API order; `priority` applies client-side review ranking on top of loaded rows. */
  const [tableSort, setTableSort] = useState<'photo' | 'priority'>('photo');
  const [resultsColumnSortBy, setResultsColumnSortBy] = useState('');
  const [resultsColumnSortDir, setResultsColumnSortDir] =
    useState<DataTableSortDirection>('asc');
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
      setResultsColumnSortBy(sortBy);
      setResultsColumnSortDir(sortDir);
      setPage(1);
    },
    []
  );

  const handleResetFilters = useCallback(() => {
    setFilter('all');
    setSkuSearch('');
    setResultsColumnSortBy('');
    setPage(1);
  }, []);

  useEffect(() => {
    setResultsColumnSortBy('');
  }, [tableSort, pickedRunJobId]);

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

  const handleClearFilterOnly = useCallback(() => setFilter('all'), []);

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
  const mergeButtonDisabled = mergeMutation.isPending || mergeCandidates.groupCount === 0;
  const mergeDisabledReason =
    mergeCandidates.groupCount === 0 ? t('positions.merge_no_skus') : '';
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
      <AisleResultsHeader
        breadcrumbs={breadcrumbs}
        title={aisle?.code ?? t('common.aisle')}
        subtitle={inventory?.name ?? (inventoryQuery.isLoading ? t('common.loading') : t('common.em_dash'))}
        assetsAction={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
            <AisleSourceAssetsManageModule
              inventoryId={inventoryId}
              aisleId={aisleId}
              inventoryLabel={inventory?.name ?? t('common.em_dash')}
              jobIdForPreview={pickedRunJobId}
              inventoryReady={Boolean(inventoryQuery.data)}
            >
              {({ openSourceAssets }) => (
                <Tooltip title={t('aisle_source_assets.action_tooltip')}>
                  <Button
                    data-testid="aisle-source-assets-manage-open"
                    size="small"
                    variant="outlined"
                    startIcon={<PhotoLibraryOutlinedIcon fontSize="small" />}
                    onClick={openSourceAssets}
                  >
                    {t('aisle_source_assets.action_label')}
                  </Button>
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
        showPromoteRun={Boolean(isTestInventory && canPromoteCurrentRun)}
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
            onReset={handleResetFilters}
            resetDisabled={filter === 'all' && !skuSearch.trim() && !resultsColumnSortBy.trim()}
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
        <AisleResultsTableSection
          countedTotal={kpi.aisleTotalCounted}
          countedResultRows={kpi.countableResults}
          mergeFeedback={mergeFeedback}
          onResetFilters={handleResetFilters}
          resetDisabled={filter === 'all' && !skuSearch.trim() && !resultsColumnSortBy.trim()}
          skuSearch={skuSearch}
          onSkuSearchChange={(v) => {
            setSkuSearch(v);
            setPage(1);
          }}
          tableSort={tableSort}
          onTableSortChange={(value) => setTableSort(value)}
          filter={filter}
          onFilterChange={(v) => {
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
          sortedForTableLength={rowsOrderedForTable.length}
          onClearFilterOnly={handleClearFilterOnly}
          tableRows={tableRows}
          onOpenReview={handleOpenReview}
          page={effectivePage}
          pageSize={pageSize}
          totalItems={rowsOrderedForTable.length}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          columnSort={{
            sortBy: resultsColumnSortBy,
            sortDir: resultsColumnSortDir,
            onSortChange: handleResultsColumnSortChange,
          }}
        />
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
      />
    </>
  );
}
