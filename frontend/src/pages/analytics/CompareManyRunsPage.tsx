import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
} from '@mui/material';
import { PageHeader } from '../../components/shell';
import { useAisleBenchmarkCompareMany, useAisleJobsList, useAislesList, useInventoryDetail } from '../../hooks';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import { getJobStatusLabel } from '../../utils/jobStatus';
import { ROUTE_HOME, pathToInventory, pathToInventoryAnalyticsCompare } from '../../constants/appRoutes';
import { formatExecutionDurationHuman, formatSignedDurationHuman } from '../../utils/benchmarkExecutionTime';
import { MAX_COMPARE_JOBS, MIN_COMPARE_JOBS } from '../../features/analytics/constants/compareManyRuns';
import { buildDraftError } from './compareManyRunsDraft';
import { compareRunExecutionLabel } from '../../features/analytics/adapters/compareFormatters';
import { formatBaselineVsTargetFromRuns } from '../../features/analytics/adapters/compareRunLabels';
import {
  buildJobsById,
  buildOrderedComparisons,
  compareManyExecutionInsight,
  isAppliedStateValid,
  orderJobsForDisplay,
  parseAppliedState,
  sameSelection,
  sortJobsForCompareManyPicker,
} from '../../features/analytics/adapters/compareManyRunsViewModel';
import CompareDeltaLegend from '../../features/analytics/components/compare/CompareDeltaLegend';
import CompareEmptyState from '../../features/analytics/components/compare/CompareEmptyState';
import CompareErrorState from '../../features/analytics/components/compare/CompareErrorState';
import CompareLoadingState from '../../features/analytics/components/compare/CompareLoadingState';
import CompareNotice from '../../features/analytics/components/compare/CompareNotice';
import CompareManyRunDraftPanel from '../../features/analytics/components/compare/CompareManyRunDraftPanel';
import CompareManySummaryCards from '../../features/analytics/components/compare/CompareManySummaryCards';
import CompareManyJobCardsGrid from '../../features/analytics/components/compare/CompareManyJobCardsGrid';
import CompareManyResultsSection from '../../features/analytics/components/compare/CompareManyResultsSection';

export default function CompareManyRunsPage() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const applied = useMemo(() => parseAppliedState(searchParams), [searchParams]);
  const correctionNoticeRef = useRef<string | null>(null);
  const [showBaselineAdjustedNotice, setShowBaselineAdjustedNotice] = useState(false);
  const [expandedTargetJobId, setExpandedTargetJobId] = useState<string | null>(null);

  const [draftOverride, setDraftOverride] = useState<{
    sourceKey: string;
    aisleId: string;
    jobIds: string[];
    baseline: string;
  } | null>(null);

  const draftSourceKey = `${applied.aisleId}|${applied.jobIds.join(',')}|${applied.baseline}`;
  const draftAisleId =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.aisleId : applied.aisleId;
  const draftJobIds =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.jobIds : applied.jobIds;
  const draftBaseline =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.baseline : applied.baseline;

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const jobsQuery = useAisleJobsList(inventoryId, draftAisleId || undefined, {
    enabled: Boolean(inventoryId && draftAisleId && inventoryQuery.data),
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
  const sortedJobsForPicker = useMemo(() => {
    return sortJobsForCompareManyPicker(jobs);
  }, [jobs]);
  const aisleSelectValue = draftAisleId && aisles.some((aisle) => aisle.id === draftAisleId) ? draftAisleId : '';
  const baselineSelectValue = draftBaseline && draftJobIds.includes(draftBaseline) ? draftBaseline : '';
  const draftError = buildDraftError(draftAisleId, draftJobIds, draftBaseline, t);
  const dirty =
    draftAisleId !== applied.aisleId || draftBaseline !== applied.baseline || !sameSelection(draftJobIds, applied.jobIds);

  /** Avoid repeated replace navigations when inventory refetches but stays non-test. */
  const nonTestRedirectInventoryRef = useRef<string | null>(null);

  useEffect(() => {
    if (!inventoryId || !inventoryQuery.isSuccess || !inventoryQuery.data) return;
    if (inventoryQuery.data.processing_mode === 'test') return;
    if (nonTestRedirectInventoryRef.current === inventoryId) return;
    nonTestRedirectInventoryRef.current = inventoryId;
    navigate(pathToInventory(inventoryId), { replace: true });
  }, [inventoryId, inventoryQuery.data, inventoryQuery.isSuccess, navigate]);

  useEffect(() => {
    // URL correction policy: only baseline is auto-corrected, and only when the rest of applied state is already valid.
    // Other invalid URL states (duplicate jobs, bad count, missing aisle) are shown as invalid without URL mutation.
    if (!applied.aisleId) return;
    if (applied.jobIds.length < MIN_COMPARE_JOBS || applied.jobIds.length > MAX_COMPARE_JOBS) return;
    if (new Set(applied.jobIds).size !== applied.jobIds.length) return;
    if (!applied.jobIds.length) return;
    if (applied.baseline && applied.jobIds.includes(applied.baseline)) return;
    const nextBaseline = applied.jobIds[0];
    if (!nextBaseline) return;
    const baselineInUrl = searchParams.get('baseline')?.trim() ?? '';
    if (baselineInUrl === nextBaseline) return;

    const correctionKey = `${applied.aisleId}|${applied.jobIds.join(',')}|${nextBaseline}`;
    // Always keep the URL canonical when baseline is wrong; the ref only gates repeating the notice.
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('baseline', nextBaseline);
      return p;
    }, { replace: true });

    if (correctionNoticeRef.current !== correctionKey) {
      correctionNoticeRef.current = correctionKey;
      setShowBaselineAdjustedNotice(true);
    }
  }, [applied.aisleId, applied.baseline, applied.jobIds, searchParams, setSearchParams]);

  const applyDraftToUrl = () => {
    if (draftError) return;
    const safeBaseline = draftJobIds.includes(draftBaseline) ? draftBaseline : draftJobIds[0] ?? '';
    if (!safeBaseline) return;
    if (safeBaseline !== draftBaseline) {
      setShowBaselineAdjustedNotice(true);
    }
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('aisleId', draftAisleId);
      p.set('jobIds', draftJobIds.join(','));
      p.set('baseline', safeBaseline);
      return p;
    });
  };

  const orderedJobIds = orderJobsForDisplay(applied.jobIds, applied.baseline);
  const jobsById = buildJobsById(effectiveData);
  const orderedComparisons = buildOrderedComparisons(effectiveData, orderedJobIds);

  const compareError = compareQuery.error || enrichedCompareManyQuery.error;
  const compareErrorMessage =
    (compareQuery.isError || enrichedCompareManyQuery.isError) && compareError
      ? getVisibleErrorMessage(compareError, 'analytics')
      : null;

  if (!inventoryId) {
    return <Alert severity="warning">{t('compare_many.missing_inventory')}</Alert>;
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
          ...(inventoryQuery.data ? [{ label: inventoryQuery.data.name, to: pathToInventory(inventoryId) }] : []),
          { label: t('analytics.compare_many_runs_breadcrumb') },
        ]}
        title={t('analytics.compare_many_runs_page_title')}
        subtitle={t('compare_many.subtitle')}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" variant="outlined" onClick={() => navigate(pathToInventoryAnalyticsCompare(inventoryId))}>
              {t('compare_many.open_ab_compare')}
            </Button>
          </Box>
        }
      />

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
        onApply={applyDraftToUrl}
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
        <Box data-testid="compare-many-results" sx={{ display: 'grid', gap: 2 }}>
          <CompareManySummaryCards
            summaryTitle={t('compare_many.summary_title')}
            summaryNotRanking={t('compare_many.summary_not_ranking')}
            summaryValuesText={t('compare_many.summary_values', {
              jobs: effectiveData.summary.job_count,
              qtyMin: effectiveData.summary.min_total_quantity,
              qtyMax: effectiveData.summary.max_total_quantity,
              reviewMin: effectiveData.summary.min_needs_review,
              reviewMax: effectiveData.summary.max_needs_review,
              consolidatedMin: effectiveData.summary.min_consolidated_positions,
              consolidatedMax: effectiveData.summary.max_consolidated_positions,
              unknownMin: effectiveData.summary.min_unknown_internal_code_count,
              unknownMax: effectiveData.summary.max_unknown_internal_code_count,
            })}
            executionCaption={
              effectiveData.summary.min_execution_time_seconds != null &&
              effectiveData.summary.max_execution_time_seconds != null
                ? t('compare_many.summary_exec_range', {
                    min: formatExecutionDurationHuman(effectiveData.summary.min_execution_time_seconds),
                    max: formatExecutionDurationHuman(effectiveData.summary.max_execution_time_seconds),
                  })
                : t('compare_many.summary_exec_unavailable')
            }
          />

          <CompareManyJobCardsGrid
            orderedJobIds={orderedJobIds}
            jobsById={jobsById}
            baselineJobId={effectiveData.baseline_job_id}
            baselineChipLabel={t('compare_many.baseline_chip')}
            statusChipLabel={(status) => t('compare_many.status_chip', { status: getJobStatusLabel(status) })}
            executionTimeLabel={(value) => t('compare_many.job_execution_time', { value })}
            executionTimeValue={(job) => compareRunExecutionLabel(job, t)}
            metricsLabel={({ qty, review, unknown, consolidated }) =>
              t('compare_many.job_metrics', { qty, review, unknown, consolidated })
            }
          />

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
    </>
  );
}
