import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Grid, Typography } from '@mui/material';
import { localizeAnalyticsSummaryNote } from '../../analytics/adapters/analyticsSummaryNotes';
import {
  buildManualInterventionViewModel,
  buildResolutionFlowStages,
  orderQualityRows,
} from '../../analytics/adapters/metricsViewModel';
import { interventionLabel, numberOrZero } from '../../analytics/adapters/metricsFormatters';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import {
  buildAutoVsManualDonutSegments,
  buildLocalizedQualityIssueChartData,
  buildManualInterventionSegments,
  buildTopAislesAttention,
  QUALITY_AISLE_ATTENTION_TOP_N,
} from '../adapters/analyticsChartDatasets';
import type { AnalyticsDrilldownHandlers } from '../types';
import { useAnalyticsTabHref } from '../hooks/useAnalyticsTabHref';
import { AnalyticsQualityOverview } from './AnalyticsQualityOverview';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import { buildQualityAisleAttentionRankingItems } from '../adapters/entityRankingViewModels';
import { AnalyticsEntityRankingCards } from './rankings/AnalyticsEntityRankingCards';
import { QualityResolutionFunnel } from './QualityResolutionFunnel';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import { SegmentBarChart } from './charts/SegmentBarChart';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsQualityTabProps {
  analytics: AnalyticsBundle;
  isLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  drilldown: AnalyticsDrilldownHandlers;
}

export function AnalyticsQualityTab({
  analytics,
  isLoading,
  inventoryProcessingModeById,
  drilldown,
}: AnalyticsQualityTabProps) {
  const { t } = useTranslation();
  const tabHref = useAnalyticsTabHref();
  const { summary, quality, manualInterventions, aisleIssues } = analytics;
  const emptyText = t('analyticsDashboard.visual.emptyChart');

  const manualInterventionViewModel = useMemo(
    () => buildManualInterventionViewModel(manualInterventions?.items),
    [manualInterventions?.items]
  );
  const qualityRowsOrdered = useMemo(() => orderQualityRows(quality?.items ?? []), [quality?.items]);
  const qualityChart = useMemo(
    () => buildLocalizedQualityIssueChartData(qualityRowsOrdered, t),
    [qualityRowsOrdered, t]
  );
  const autoManualDonut = useMemo(() => buildAutoVsManualDonutSegments(summary, t), [summary, t]);
  const manualSegments = useMemo(
    () => buildManualInterventionSegments(manualInterventions?.items, t),
    [manualInterventions?.items, t]
  );

  const localizedSummaryNotes = useMemo(
    () => (summary?.notes ?? []).map((n) => localizeAnalyticsSummaryNote(n, t)),
    [summary?.notes, t]
  );

  const pendingReviewCount = useMemo(
    () => (aisleIssues?.items ?? []).reduce((sum, row) => sum + numberOrZero(row.needs_review_count), 0),
    [aisleIssues?.items]
  );

  const processedPositionsCount = summary?.processed_positions_count ?? 0;

  const resolutionFlowStages = useMemo(
    () =>
      buildResolutionFlowStages(
        {
          totalPositionsCount: summary?.total_positions_in_scope ?? summary?.positions_in_scope ?? 0,
          pendingReviewCount,
          processedPositionsCount,
          reviewedPositionsCount: summary?.reviewed_positions_count ?? 0,
          interventionPositionsCount: manualInterventions?.intervention_positions_count ?? 0,
          operatorMarkedUnknownCount: summary?.operator_marked_unknown_count ?? summary?.unknown_count ?? 0,
          hasOperatorUnknownRate: (summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null,
        },
        t
      ),
    [
      t,
      summary,
      pendingReviewCount,
      processedPositionsCount,
      manualInterventions?.intervention_positions_count,
    ]
  );

  const topAisles = useMemo(
    () => buildTopAislesAttention(aisleIssues?.items ?? [], QUALITY_AISLE_ATTENTION_TOP_N),
    [aisleIssues?.items]
  );
  const qualityAisleRankingItems = useMemo(
    () =>
      buildQualityAisleAttentionRankingItems({
        rows: topAisles,
        inventoryProcessingModeById,
        onOpenAisleDrilldown: drilldown.onOpenAisleDrilldown,
        t,
      }),
    [topAisles, inventoryProcessingModeById, drilldown.onOpenAisleDrilldown, t]
  );

  const unsupportedCaption = manualInterventionViewModel.unsupportedInterventions
    .map((item) => interventionLabel(item.category, t))
    .join(', ');

  return (
    <Box data-testid="analytics-quality-tab">
      {localizedSummaryNotes.length > 0 ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="analytics-quality-warnings">
          {localizedSummaryNotes.join(' ')}
        </Alert>
      ) : null}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.quality.overviewTitle')}
            isLoading={isLoading}
            loadingSkeletonHeight={200}
            data-testid="analytics-quality-panel-overview"
          >
            <AnalyticsQualityOverview
              chartTitle={t('analyticsDashboard.visual.autoVsManual')}
              donutSegments={autoManualDonut}
              pendingReviewCount={pendingReviewCount}
              processedPositionsCount={processedPositionsCount}
              pendingLabel={t('analyticsDashboard.quality.kpiPending')}
              processedLabel={t('analyticsDashboard.quality.kpiProcessed')}
              emptyText={emptyText}
              data-testid="analytics-quality-overview"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.quality.resolutionTitle')}
            subtitle={t('analyticsDashboard.quality.resolutionSubtitle')}
            isLoading={isLoading}
            loadingSkeletonHeight={200}
            data-testid="analytics-quality-panel-resolution"
          >
            <QualityResolutionFunnel
              stages={resolutionFlowStages}
              emptyText={emptyText}
              data-testid="analytics-quality-resolution-funnel"
            />
            <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2.5, mb: 1 }}>
              {t('analyticsDashboard.quality.manualTitle')}
            </Typography>
            <SegmentBarChart
              segments={manualSegments}
              emptyText={t('analytics.no_manual_interventions_scope')}
              data-testid="analytics-quality-manual-chart"
            />
            {unsupportedCaption ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                {t('analyticsDashboard.quality.unsupportedCategories', { categories: unsupportedCaption })}
              </Typography>
            ) : null}
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.quality.issuesTitle')}
            isLoading={isLoading}
            data-testid="analytics-quality-panel-issues"
          >
            <HorizontalBarChart
              data={qualityChart}
              emptyText={emptyText}
              ariaLabel={t('analyticsDashboard.quality.issuesTitle')}
              data-testid="analytics-quality-issues-bars"
            />
          </AnalyticsSummaryPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.quality.aislesTitle')}
            ctaLabel={t('analyticsDashboard.quality.viewAislesDetail')}
            ctaHref={tabHref('aisles')}
            data-testid="analytics-quality-panel-aisles"
          >
            <AnalyticsEntityRankingCards
              items={qualityAisleRankingItems}
              emptyText={emptyText}
              testId="analytics-quality-aisle-ranking"
            />
          </AnalyticsSummaryPanel>
        </Grid>
      </Grid>
    </Box>
  );
}
