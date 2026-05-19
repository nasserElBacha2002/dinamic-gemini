import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { formatCostCell } from '../adapters/analyticsCostViewModel';
import { AnalyticsEntityActionRow } from './AnalyticsEntityActionRow';

type AisleCostRow = AnalyticsCostSummaryResponse['by_aisle'][number];

export interface AnalyticsCostAisleRankingCardsProps {
  rows: readonly AisleCostRow[];
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  emptyText: string;
}

export function AnalyticsCostAisleRankingCards({
  rows,
  onOpenAisleDrilldown,
  emptyText,
}: AnalyticsCostAisleRankingCardsProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-cost-aisle-ranking-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box data-testid="analytics-cost-aisle-ranking" sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {rows.map((row) => (
        <Paper
          key={row.aisle_id}
          variant="outlined"
          data-testid={`analytics-cost-aisle-card-${row.aisle_id}`}
          sx={{ p: 1.25 }}
        >
          <Typography variant="body2" fontWeight={700}>
            {row.aisle_code ?? row.aisle_id}
            <Typography component="span" variant="body2" color="text.secondary" fontWeight={400}>
              {' · '}
              {row.inventory_name ?? row.inventory_id}
            </Typography>
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 0.75, mb: 1, mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.totalCost')}: {formatCostCell(row.total_cost, 'cost', t)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.totalQuantity')}: {formatCostCell(row.total_counted_quantity, 'quantity', t)}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ gridColumn: '1 / -1' }}>
              {t('analyticsDashboard.costs.costPerUnit')}: {formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}
            </Typography>
          </Box>
          <AnalyticsEntityActionRow
            analyticsLabel={t('analyticsDashboard.drilldown.openAnalytics')}
            onAnalyticsClick={() => onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
            analyticsTestId={`cost-drilldown-aisle-${row.aisle_id}`}
            compareLabel={t('analyticsDashboard.aisles.compareRuns')}
            compareDisabled
          />
        </Paper>
      ))}
    </Box>
  );
}
