import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import { pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import type { InventoryPerformanceRow } from '../../analytics/types';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { formatAvgProcessingMinutes, formatPct } from '../../analytics/adapters/metricsFormatters';
import { formatCostCellWithLoading } from '../adapters/analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';
import { AnalyticsEntityActionRow } from './AnalyticsEntityActionRow';

export interface AnalyticsInventoryRankingCardsProps {
  rows: readonly InventoryPerformanceRow[];
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  costByInventory: ReadonlyMap<string, { total_cost?: number | null; total_counted_quantity?: number | null; cost_per_counted_unit?: number | null }>;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenInventoryDrilldown: (inventoryId: string) => void;
  emptyText: string;
}

export function AnalyticsInventoryRankingCards({
  rows,
  costByInventory,
  isCostLoading,
  inventoryProcessingModeById,
  onOpenInventoryDrilldown,
  emptyText,
}: AnalyticsInventoryRankingCardsProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-inventories-ranking-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box
      data-testid="analytics-inventories-ranking"
      sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}
    >
      {rows.map((row) => {
        const cost = costByInventory.get(row.inventory_id);
        const eligibility = getCompareEligibility(inventoryProcessingModeById.get(row.inventory_id));
        const compareHref = eligibility.allowed ? pathToInventoryAnalyticsCompareMany(row.inventory_id) : '';

        return (
          <Paper
            key={row.inventory_id}
            variant="outlined"
            data-testid={`analytics-inventory-card-${row.inventory_id}`}
            sx={{ p: 1.5 }}
          >
            <Typography variant="body2" fontWeight={700} gutterBottom>
              {row.inventory_name}
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                gap: 1,
                mb: 1,
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {t('analytics.column_auto_accept')}: {formatPct(row.auto_acceptance_rate)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('analyticsDashboard.costs.totalCost')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.total_cost, 'cost', t)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('analyticsDashboard.costs.totalQuantity')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.total_counted_quantity, 'quantity', t)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('analyticsDashboard.costs.costPerUnit')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.cost_per_counted_unit, 'costPerUnit', t)}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ gridColumn: '1 / -1' }}>
                {t('analytics.column_avg_processing')}:{' '}
                {formatAvgProcessingMinutes(row.average_processing_time_minutes, null)}
              </Typography>
            </Box>
            <AnalyticsEntityActionRow
              viewDetailLabel={t('analyticsDashboard.inventories.viewDetail')}
              viewDetailHref={pathToInventory(row.inventory_id)}
              viewDetailTestId={`inventory-view-detail-${row.inventory_id}`}
              analyticsLabel={t('analyticsDashboard.inventories.openAnalytics')}
              onAnalyticsClick={() => onOpenInventoryDrilldown(row.inventory_id)}
              analyticsTestId={`inventory-drilldown-${row.inventory_id}`}
              compareLabel={t('analyticsDashboard.inventories.compareRuns')}
              compareHref={compareHref}
              compareDisabled={!eligibility.allowed}
              compareTooltip={eligibility.allowed ? '' : t(compareEligibilityTooltipKey(eligibility.reason))}
              compareTestId={`inventory-compare-${row.inventory_id}`}
            />
          </Paper>
        );
      })}
    </Box>
  );
}
