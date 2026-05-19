import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Collapse, Grid, Paper, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { MetricUnavailableState } from './MetricUnavailableState';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import { AnalyticsCostAisleRankingCards } from './AnalyticsCostAisleRankingCards';
import { AnalyticsCostInventoryRankingCards } from './AnalyticsCostInventoryRankingCards';
import { AnalyticsCostTabularDetail } from './AnalyticsCostTabularDetail';
import { AnalyticsCompactKpiGrid } from './AnalyticsCompactKpiGrid';
import { AnalyticsSummaryPanel } from './AnalyticsSummaryPanel';
import {
  buildCaptureStatusDonutSegments,
  buildCostByProviderChartData,
  buildJobsCoverageDonutSegments,
  buildTopCostAisleRows,
  buildTopCostInventoryRows,
} from '../adapters/analyticsChartDatasets';
import {
  buildOverviewCostKpis,
  buildCostWarnings,
  costSummaryEmptyMessage,
  getCostSummaryEmptyKind,
  hasCostData,
} from '../adapters/analyticsCostViewModel';
import { DonutChart } from './charts/DonutChart';
import { HorizontalBarChart } from './charts/HorizontalBarChart';
import type { AnalyticsDrilldownHandlers } from '../types';

export interface AnalyticsCostsTabProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isError: boolean;
  onGoToCompare: () => void;
  drilldown: AnalyticsDrilldownHandlers;
}

function CompareCostsCallout({ onGoToCompare }: { onGoToCompare: () => void }) {
  const { t } = useTranslation();
  return (
    <Paper
      variant="outlined"
      data-testid="analytics-costs-compare-callout"
      sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
    >
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {t('analyticsDashboard.costs.perCompareSectionTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('analyticsDashboard.costs.compareAvailableDescription')}
      </Typography>
      <Button variant="outlined" onClick={onGoToCompare} data-testid="analytics-costs-go-compare" sx={{ alignSelf: 'flex-start' }}>
        {t('analyticsDashboard.costs.goToCompare')}
      </Button>
    </Paper>
  );
}

export function AnalyticsCostsTab({
  costSummary,
  isLoading,
  isError,
  onGoToCompare,
  drilldown,
}: AnalyticsCostsTabProps) {
  const { t } = useTranslation();
  const [tabularOpen, setTabularOpen] = useState(false);
  const emptyText = t('analyticsDashboard.visual.emptyChart');

  const warnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const emptyKind = useMemo(() => getCostSummaryEmptyKind(costSummary), [costSummary]);
  const overviewKpis = useMemo(
    () =>
      buildOverviewCostKpis(costSummary, t).map((card, index) => ({
        id: `cost-kpi-${index}`,
        label: card.label,
        value: card.value,
      })),
    [costSummary, t]
  );
  const providerChart = useMemo(() => buildCostByProviderChartData(costSummary), [costSummary]);
  const captureDonut = useMemo(() => buildCaptureStatusDonutSegments(costSummary, t), [costSummary, t]);
  const jobsDonut = useMemo(() => buildJobsCoverageDonutSegments(costSummary, t), [costSummary, t]);
  const topInventories = useMemo(() => buildTopCostInventoryRows(costSummary), [costSummary]);
  const topAisles = useMemo(() => buildTopCostAisleRows(costSummary), [costSummary]);

  if (isError) {
    return (
      <Box data-testid="analytics-costs-tab">
        <MetricUnavailableState
          title={t('analyticsDashboard.costs.loadError')}
          description={t('analyticsDashboard.costs.loadErrorDetail')}
        />
        <CompareCostsCallout onGoToCompare={onGoToCompare} />
      </Box>
    );
  }

  const showEmpty = !isLoading && emptyKind != null;

  return (
    <Box data-testid="analytics-costs-tab">
      {showEmpty ? (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="analytics-costs-empty">
            {costSummaryEmptyMessage(emptyKind, t)}
          </Typography>
          <CompareCostsCallout onGoToCompare={onGoToCompare} />
        </>
      ) : (
        <>
          <AnalyticsCostWarningsBlock warnings={warnings} summary />

          <AnalyticsSummaryPanel
            title={t('analyticsDashboard.costs.executiveSummaryTitle')}
            subtitle={t('analyticsDashboard.costs.llmCostHint')}
            isLoading={isLoading && !hasCostData(costSummary)}
            loadingSkeletonHeight={88}
            data-testid="analytics-costs-panel-executive"
          >
            <AnalyticsCompactKpiGrid items={overviewKpis} data-testid="analytics-costs-executive-kpis" />
          </AnalyticsSummaryPanel>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={6}>
              <AnalyticsSummaryPanel
                title={t('analyticsDashboard.visual.captureStatusDistribution')}
                isLoading={isLoading}
                data-testid="analytics-costs-panel-capture"
              >
                <DonutChart
                  segments={captureDonut}
                  emptyText={emptyText}
                  data-testid="analytics-costs-capture-donut"
                />
              </AnalyticsSummaryPanel>
            </Grid>
            <Grid item xs={12} md={6}>
              <AnalyticsSummaryPanel
                title={t('analyticsDashboard.costs.jobsCoverageTitle')}
                isLoading={isLoading}
                data-testid="analytics-costs-panel-jobs-coverage"
              >
                <DonutChart
                  segments={jobsDonut}
                  emptyText={emptyText}
                  data-testid="analytics-costs-jobs-coverage-donut"
                />
              </AnalyticsSummaryPanel>
            </Grid>

            <Grid item xs={12} md={6}>
              <AnalyticsSummaryPanel
                title={t('analyticsDashboard.visual.costByProviderModel')}
                subtitle={t('analyticsDashboard.visual.notARecommendation')}
                isLoading={isLoading}
                data-testid="analytics-costs-panel-provider"
              >
                <HorizontalBarChart
                  data={providerChart}
                  emptyText={emptyText}
                  data-testid="analytics-costs-chart-provider-bars"
                />
              </AnalyticsSummaryPanel>
            </Grid>

            <Grid item xs={12} md={6}>
              <AnalyticsSummaryPanel
                title={t('analyticsDashboard.costs.byInventoryTitle')}
                isLoading={isLoading}
                data-testid="analytics-costs-panel-inventory"
              >
                <AnalyticsCostInventoryRankingCards
                  rows={topInventories}
                  onOpenInventoryDrilldown={drilldown.onOpenInventoryDrilldown}
                  emptyText={emptyText}
                />
              </AnalyticsSummaryPanel>
            </Grid>

            <Grid item xs={12} md={6}>
              <AnalyticsSummaryPanel
                title={t('analyticsDashboard.costs.byAisleTitle')}
                isLoading={isLoading}
                data-testid="analytics-costs-panel-aisle"
              >
                <AnalyticsCostAisleRankingCards
                  rows={topAisles}
                  onOpenAisleDrilldown={drilldown.onOpenAisleDrilldown}
                  emptyText={emptyText}
                />
              </AnalyticsSummaryPanel>
            </Grid>

            <Grid item xs={12} md={6}>
              <CompareCostsCallout onGoToCompare={onGoToCompare} />
            </Grid>
          </Grid>

          <Box sx={{ mb: 2 }}>
            <Button
              size="small"
              variant="text"
              onClick={() => setTabularOpen((open) => !open)}
              data-testid="analytics-costs-toggle-tabular"
              sx={{ px: 0 }}
            >
              {tabularOpen
                ? t('analyticsDashboard.costs.hideTabularDetail')
                : t('analyticsDashboard.costs.showTabularDetail')}
            </Button>
            <Collapse in={tabularOpen} unmountOnExit>
              <AnalyticsCostTabularDetail costSummary={costSummary} />
            </Collapse>
          </Box>
        </>
      )}
    </Box>
  );
}
