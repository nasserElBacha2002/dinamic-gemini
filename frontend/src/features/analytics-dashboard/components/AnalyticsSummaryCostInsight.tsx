import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import {
  buildCaptureStatusDonutSegments,
  buildCostByProviderChartData,
} from '../adapters/analyticsChartDatasets';
import { DonutChart } from './charts/DonutChart';
import { HorizontalBarChart } from './charts/HorizontalBarChart';

export interface AnalyticsSummaryCostInsightProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  warningLine?: string | null;
}

export function AnalyticsSummaryCostInsight({ costSummary, warningLine }: AnalyticsSummaryCostInsightProps) {
  const { t } = useTranslation();
  const emptyText = t('analyticsDashboard.visual.emptyChart');

  const captureDonut = useMemo(
    () => buildCaptureStatusDonutSegments(costSummary, t),
    [costSummary, t]
  );
  const topProviders = useMemo(() => buildCostByProviderChartData(costSummary).slice(0, 3), [costSummary]);

  return (
    <Box data-testid="analytics-summary-cost-insight">
      {warningLine ? (
        <Typography variant="caption" color="warning.main" display="block" sx={{ mb: 1.5 }}>
          {warningLine}
        </Typography>
      ) : null}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
          gap: 2,
          alignItems: 'start',
        }}
      >
        <Box data-testid="analytics-summary-cost-donut-wrap">
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('analyticsDashboard.visual.captureStatusDistribution')}
          </Typography>
          <DonutChart
            segments={captureDonut}
            emptyText={emptyText}
            data-testid="analytics-summary-cost-donut"
          />
        </Box>
        <Box data-testid="analytics-summary-cost-ranking-wrap">
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('analyticsDashboard.visual.costByProviderModel')}
          </Typography>
          <HorizontalBarChart
            data={topProviders}
            emptyText={emptyText}
            ariaLabel={t('analyticsDashboard.visual.costByProviderModel')}
            data-testid="analytics-summary-cost-provider-bars"
          />
        </Box>
      </Box>
    </Box>
  );
}
