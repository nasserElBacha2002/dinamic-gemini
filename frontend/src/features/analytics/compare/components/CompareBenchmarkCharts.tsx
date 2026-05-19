import { Box } from '@mui/material';
import { AnalyticsChartCard } from '../../../analytics-dashboard/components/AnalyticsChartCard';
import { HorizontalBarChart } from '../../../analytics-dashboard/components/charts/HorizontalBarChart';
import type { CompareBenchmarkChartsModel } from '../compareBenchmarkViewModel';

type CompareBenchmarkChartsProps = {
  charts: CompareBenchmarkChartsModel;
  compact?: boolean;
};

export default function CompareBenchmarkCharts({ charts, compact = false }: CompareBenchmarkChartsProps) {
  const chartItems = [
    { key: 'cost', ...charts.costPerRun, testId: 'compare-chart-cost-per-run' },
    { key: 'cpu', ...charts.costPerUnit, testId: 'compare-chart-cost-per-unit', subtitle: charts.costPerUnit.subtitle },
    { key: 'time', ...charts.executionTime, testId: 'compare-chart-execution-time' },
    { key: 'qty', ...charts.quantity, testId: 'compare-chart-quantity', subtitle: charts.quantity.subtitle },
    { key: 'review', ...charts.reviewRequired, testId: 'compare-chart-review', subtitle: charts.reviewRequired.subtitle },
    { key: 'unknown', ...charts.unknownCodes, testId: 'compare-chart-unknown-codes' },
  ] as const;

  return (
    <Box
      data-testid="compare-benchmark-charts"
      sx={{
        display: 'grid',
        gap: compact ? 1.5 : 2,
        gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
      }}
    >
      {chartItems.map((item) => (
        <AnalyticsChartCard
          key={item.key}
          title={item.title}
          subtitle={'subtitle' in item ? item.subtitle : undefined}
          empty={!item.data.length}
          emptyText={item.emptyText}
          data-testid={`${item.testId}-card`}
        >
          <HorizontalBarChart data={item.data} emptyText={item.emptyText} data-testid={item.testId} />
        </AnalyticsChartCard>
      ))}
    </Box>
  );
}
