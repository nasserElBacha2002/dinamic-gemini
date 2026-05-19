import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { formatCostCell } from '../adapters/analyticsCostViewModel';
import { AnalyticsEntityActionRow } from './AnalyticsEntityActionRow';

type InventoryCostRow = AnalyticsCostSummaryResponse['by_inventory'][number];

export interface AnalyticsCostInventoryRankingCardsProps {
  rows: readonly InventoryCostRow[];
  onOpenInventoryDrilldown: (inventoryId: string) => void;
  emptyText: string;
}

export function AnalyticsCostInventoryRankingCards({
  rows,
  onOpenInventoryDrilldown,
  emptyText,
}: AnalyticsCostInventoryRankingCardsProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-cost-inventory-ranking-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box data-testid="analytics-cost-inventory-ranking" sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {rows.map((row) => (
        <Paper key={row.inventory_id} variant="outlined" data-testid={`analytics-cost-inventory-card-${row.inventory_id}`} sx={{ p: 1.25 }}>
          <Typography variant="body2" fontWeight={700} gutterBottom>
            {row.inventory_name ?? row.inventory_id}
          </Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 0.75, mb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.totalCost')}: {formatCostCell(row.total_cost, 'cost', t)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.totalQuantity')}: {formatCostCell(row.total_counted_quantity, 'quantity', t)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.costPerUnit')}: {formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('analyticsDashboard.costs.jobsWithCost')}: {formatCostCell(row.jobs_with_cost, 'integer', t)}
            </Typography>
          </Box>
          <AnalyticsEntityActionRow
            analyticsLabel={t('analyticsDashboard.drilldown.openAnalytics')}
            onAnalyticsClick={() => onOpenInventoryDrilldown(row.inventory_id)}
            analyticsTestId={`cost-drilldown-inventory-${row.inventory_id}`}
            compareLabel={t('analyticsDashboard.inventories.compareRuns')}
            compareDisabled
          />
        </Paper>
      ))}
    </Box>
  );
}
