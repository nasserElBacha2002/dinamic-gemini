import { useEffect, useMemo, useRef, useState } from 'react';
import {
  buildCompareBenchmarkCharts,
  buildCompareExecutiveSummary,
  buildDeltaKpiModels,
  buildRunBenchmarkCards,
} from './compareBenchmarkViewModel';
import CompareBenchmarkCharts from './components/CompareBenchmarkCharts';
import CompareBenchmarkRunCards from './components/CompareBenchmarkRunCards';
import CompareContextWarnings from './components/CompareContextWarnings';
import CompareDeltaKpiRow from './components/CompareDeltaKpiRow';
import CompareExecutiveSummary from './components/CompareExecutiveSummary';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Box, Button, Typography } from '@mui/material';
import { PageHeader } from '../../../components/shell';
import { useAisleBenchmarkCompareMany, useAisleJobsList, useAislesList, useInventoryDetail } from '../../../hooks';
import { getVisibleErrorMessage } from '../../../utils/apiErrors';
import { ROUTE_HOME, pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { formatSignedDurationHuman } from '../../../utils/benchmarkExecutionTime';
import { MAX_COMPARE_JOBS } from '../constants/compareManyRuns';
import { buildDraftError } from './compareManyRunsDraft';
import { formatBaselineVsTargetFromRuns } from '../adapters/compareRunLabels';
import {
  buildJobsById,
  buildOrderedComparisons,
  compareManyExecutionInsight,
  isAppliedStateValid,
  orderJobsForDisplay,
  sortJobsForCompareManyPicker,
} from '../adapters/compareManyRunsViewModel';
import CompareDeltaLegend from '../components/compare/CompareDeltaLegend';
import CompareEmptyState from '../components/compare/CompareEmptyState';
import CompareErrorState from '../components/compare/CompareErrorState';
import CompareLoadingState from '../components/compare/CompareLoadingState';
import CompareNotice from '../components/compare/CompareNotice';
import CompareManyRunDraftPanel from '../components/compare/CompareManyRunDraftPanel';
import CompareManyResultsSection from '../components/compare/CompareManyResultsSection';
import {
  type CompareManyRunsWorkspaceMode,
  useCompareManyAppliedState,
} from './useCompareManyAppliedState';

export interface CompareManyRunsWorkspaceProps {
  mode: CompareManyRunsWorkspaceMode;
  inventoryId: string;
  initialAisleId?: string;
  initialJobIds?: string[];
  initialBaselineJobId?: string;
  inventoryName?: string | null;
  onNavigateToStandalone?: (href: string) => void;
}

export function CompareManyRunsWorkspace({
  mode,
  inventoryId,
  initialAisleId,
  initialJobIds,
  initialBaselineJobId,
  inventoryName,
  onNavigateToStandalone,
}: CompareManyRunsWorkspaceProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const isEmbedded = mode === 'embedded';

  const {
    applied,
    draftAisleId,
    draftJobIds,
    draftBaseline,
    draftSourceKey,
    dirty,
    showBaselineAdjustedNotice,
    setShowBaselineAdjustedNotice,
    setDraftOverride,
    applyDraft,
  } = useCompareManyAppliedState({
    mode,
    initialAisleId,
    initialJobIds,
    initialBaselineJobId,
  });

  const [expandedTargetJobId, setExpandedTargetJobId] = useState<string | null>(null);

  const inventoryQuery = useInventoryDetail(inventoryId, {
    enabled: !isEmbedded && Boolean(inventoryId),
  });
  const inventoryContextReady = isEmbedded || Boolean(inventoryQuery.data);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryContextReady),
  });
  const jobsQuery = useAisleJobsList(inventoryId, draftAisleId || undefined, {
    enabled: Boolean(inventoryId && draftAisleId && inventoryContextReady),
    limit: 200,
  });

  const appliedValid = isAppliedStateValid(applied);
  const compareQuery = useAisleBenchmarkCompareMany(
    inventoryId,
    applied.aisleId || undefined,
    applied.jobIds,
    applied.baseline,
    { enabled: appliedValid, includeDiffRows: false }
  );
  const enrichedCompareManyQuery = useAisleBenchmarkCompareMany(
    inventoryId,
    applied.aisleId || undefined,
    applied.jobIds,
    applied.baseline,
    { enabled: appliedValid && Boolean(expandedTargetJobId), includeDiffRows: true }
  );

  // Expanding one block enriches the full compare-many payload (all comparisons), then each block renders its own slice.
  const effectiveData = enrichedCompareManyQuery.data ?? compareQuery.data;
  const aisles = aislesQuery.data?.items ?? [];
  const jobs = useMemo(() => jobsQuery.data?.jobs ?? [], [jobsQuery.data?.jobs]);
  const sortedJobsForPicker = useMemo(() => sortJobsForCompareManyPicker(jobs), [jobs]);
  const aisleSelectValue = draftAisleId && aisles.some((aisle) => aisle.id === draftAisleId) ? draftAisleId : '';
  const baselineSelectValue = draftBaseline && draftJobIds.includes(draftBaseline) ? draftBaseline : '';
  const draftError = buildDraftError(draftAisleId, draftJobIds, draftBaseline, t);

  const nonTestRedirectInventoryRef = useRef<string | null>(null);

  useEffect(() => {
    if (isEmbedded) return;
    if (!inventoryId || !inventoryQuery.isSuccess || !inventoryQuery.data) return;
    if (inventoryQuery.data.processing_mode === 'test') return;
    if (nonTestRedirectInventoryRef.current === inventoryId) return;
    nonTestRedirectInventoryRef.current = inventoryId;
    navigate(pathToInventory(inventoryId), { replace: true });
  }, [inventoryId, inventoryQuery.data, inventoryQuery.isSuccess, isEmbedded, navigate]);

  const orderedJobIds = orderJobsForDisplay(applied.jobIds, applied.baseline);
  const jobsById = buildJobsById(effectiveData);
  const orderedComparisons = buildOrderedComparisons(effectiveData, orderedJobIds);

  const benchmarkExecutiveSummary = useMemo(
    () => (effectiveData ? buildCompareExecutiveSummary(effectiveData, t) : null),
    [effectiveData, t]
  );
  const benchmarkRunCards = useMemo(
    () => (effectiveData ? buildRunBenchmarkCards(effectiveData, orderedJobIds, t) : []),
    [effectiveData, orderedJobIds, t]
  );
  const benchmarkDeltaRows = useMemo(
    () =>
      effectiveData ? buildDeltaKpiModels(effectiveData, jobsById, orderedComparisons, t) : [],
    [effectiveData, jobsById, orderedComparisons, t]
  );
  const benchmarkCharts = useMemo(
    () => (effectiveData ? buildCompareBenchmarkCharts(effectiveData, orderedJobIds, t) : null),
    [effectiveData, orderedJobIds, t]
  );

  const compareError = compareQuery.error || enrichedCompareManyQuery.error;
  const compareErrorMessage =
    (compareQuery.isError || enrichedCompareManyQuery.isError) && compareError
      ? getVisibleErrorMessage(compareError, 'analytics')
      : null;

  const standaloneHref = pathToInventoryAnalyticsCompareMany(inventoryId, {
    aisleId: applied.aisleId || initialAisleId || undefined,
    jobIds: applied.jobIds.length > 0 ? applied.jobIds : undefined,
    baseline: applied.baseline || undefined,
  });

  const handleOpenStandalone = () => {
    if (onNavigateToStandalone) {
      onNavigateToStandalone(standaloneHref);
      return;
    }
    void navigate(standaloneHref);
  };

  return (
    <Box data-testid={isEmbedded ? 'compare-many-workspace-embedded' : 'compare-many-workspace-route'}>
      {!isEmbedded ? (
        <PageHeader
          breadcrumbs={[
            { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
            ...(inventoryQuery.data ? [{ label: inventoryQuery.data.name, to: pathToInventory(inventoryId) }] : []),
            { label: t('analytics.compare_many_runs_breadcrumb') },
          ]}
          title={t('analytics.compare_many_runs_page_title')}
          subtitle={t('compare_many.subtitle')}
        />
      ) : (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle1" fontWeight={600} gutterBottom>
            {t('analyticsDashboard.compare.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
            {t('analyticsDashboard.compare.embeddedSubtitle')}
          </Typography>
          {inventoryName ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              {t('common.inventory')}: {inventoryName}
            </Typography>
          ) : null}
          <Typography variant="caption" color="text.secondary" display="block">
            {t('analyticsDashboard.compare.quantityDeltaNeutral')}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('analyticsDashboard.compare.notRecommendation')}
          </Typography>
          <Button
            size="small"
            variant="outlined"
            data-testid="analytics-open-compare-fullscreen"
            onClick={handleOpenStandalone}
          >
            {t('analyticsDashboard.compare.openFullscreen')}
          </Button>
        </Box>
      )}

      {showBaselineAdjustedNotice ? (
        <CompareNotice
          severity="info"
          sx={{ mb: 2 }}
          message={t('compare_many.baseline_adjusted_notice')}
          onClose={() => {
            setShowBaselineAdjustedNotice(false);
          }}
        />
      ) : null}

      <CompareManyRunDraftPanel
        aisles={aisles}
        jobs={sortedJobsForPicker}
        jobsForDisplayFallback={jobs}
        draftAisleId={aisleSelectValue}
        draftJobIds={draftJobIds}
        baselineSelectValue={baselineSelectValue}
        maxCompareJobs={MAX_COMPARE_JOBS}
        dirty={dirty}
        draftError={draftError}
        onAisleChange={(nextAisleId) =>
          setDraftOverride({
            sourceKey: draftSourceKey,
            aisleId: nextAisleId,
            jobIds: [],
            baseline: '',
          })
        }
        onDraftJobIdsChange={(next) => {
          const nextBaseline = next.includes(draftBaseline) ? draftBaseline : (next[0] ?? '');
          setDraftOverride({
            sourceKey: draftSourceKey,
            aisleId: draftAisleId,
            jobIds: next,
            baseline: nextBaseline,
          });
        }}
        onBaselineChange={(nextBaseline) =>
          setDraftOverride({
            sourceKey: draftSourceKey,
            aisleId: draftAisleId,
            jobIds: draftJobIds,
            baseline: nextBaseline,
          })
        }
        onApply={() =>
          applyDraft(
            { aisleId: draftAisleId, jobIds: draftJobIds, baseline: draftBaseline },
            draftError
          )
        }
        aisleLabel={t('common.aisle')}
        jobsLabel={t('compare_many.job_ids_label')}
        baselineLabel={t('compare_many.baseline_label')}
        applyLabel={t('compare_many.apply')}
        dirtyLabel={t('compare_many.changes_not_applied')}
      />

      {!appliedValid ? (
        <CompareEmptyState message={t('compare_many.empty_instruction')} testId="compare-many-empty-state" />
      ) : null}

      {compareErrorMessage ? <CompareErrorState message={compareErrorMessage} sx={{ mb: 2 }} /> : null}

      {appliedValid && (compareQuery.isFetching || (!compareQuery.data && compareQuery.isLoading)) ? (
        <CompareLoadingState testId="compare-many-loading" skeletonHeights={[80, 120, 160]} />
      ) : null}

      {effectiveData ? (
        <Box data-testid="compare-many-results" sx={{ display: 'grid', gap: isEmbedded ? 1.5 : 2 }}>
          <CompareContextWarnings data={effectiveData} compact={isEmbedded} />

          {benchmarkExecutiveSummary ? (
            <CompareExecutiveSummary model={benchmarkExecutiveSummary} compact={isEmbedded} />
          ) : null}

          <CompareBenchmarkRunCards cards={benchmarkRunCards} compact={isEmbedded} />

          <CompareDeltaKpiRow rows={benchmarkDeltaRows} compact={isEmbedded} />

          {benchmarkCharts ? <CompareBenchmarkCharts charts={benchmarkCharts} compact={isEmbedded} /> : null}

          <CompareDeltaLegend
            title={t('compare_many.delta_legend_title')}
            body={t('compare_many.delta_legend_body')}
          />

          <CompareManyResultsSection
            orderedComparisons={orderedComparisons}
            expandedTargetJobId={expandedTargetJobId}
            isEnrichedFetching={enrichedCompareManyQuery.isFetching}
            hasEnrichedData={Boolean(enrichedCompareManyQuery.data)}
            targetStatusByJobId={new Map((effectiveData.jobs ?? []).map((job) => [job.job_id, job.status]))}
            onToggleExpanded={(targetJobId, expanded) => setExpandedTargetJobId(expanded ? null : targetJobId)}
            insightText={(comp) => compareManyExecutionInsight(t, comp as never)}
            deltaExecutionLabel={(value) => formatSignedDurationHuman(value)}
            baselineVsTargetLabel={(baseline, target) => t('compare_many.baseline_vs_target', { baseline, target })}
            comparisonTitleForJobIds={(bId, tId) => formatBaselineVsTargetFromRuns(bId, tId, jobsById, t)}
            diffSummaryLabel={({ onlyBaseline, onlyTarget, both, qty, sku, pos }) =>
              t('compare_many.diff_summary_stats', { onlyBaseline, onlyTarget, both, qty, sku, pos })
            }
            labels={{
              hide: t('common.hide'),
              showDiffRows: t('compare_many.show_diff_rows'),
              targetNonIdealStatus: t('compare_many.target_non_ideal_status'),
              deltaNeedsReview: (value) => t('compare_many.delta_needs_review', { value }),
              deltaUnknown: (value) => t('compare_many.delta_unknown', { value }),
              deltaTotalQty: (value) => t('compare_many.delta_total_qty', { value }),
              deltaConsolidated: (value) => t('compare_many.delta_consolidated', { value }),
              deltaExecutionTime: (value) => t('compare_many.delta_execution_time', { value }),
              noDifferences: t('compare_many.no_differences'),
              loadingDiffRows: t('compare_many.loading_diff_rows'),
              noDiffRows: t('compare.no_diff_rows'),
              colKey: t('compare.col_key'),
              colSide: t('compare.col_side'),
              colQtyA: t('compare.col_qty_a'),
              colQtyB: t('compare.col_qty_b'),
              colSkuA: t('compare.col_sku_a'),
              colSkuB: t('compare.col_sku_b'),
              colPosA: t('compare.col_pos_a'),
              colPosB: t('compare.col_pos_b'),
              emDash: t('common.em_dash'),
            }}
          />
        </Box>
      ) : null}
    </Box>
  );
}
