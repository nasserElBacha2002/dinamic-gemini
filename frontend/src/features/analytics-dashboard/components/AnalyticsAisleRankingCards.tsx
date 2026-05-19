import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import { pathToAislePositions, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import type { AisleIssueRow } from '../../analytics/types';
import { formatCostCellWithLoading } from '../adapters/analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';
import { AnalyticsEntityActionRow } from './AnalyticsEntityActionRow';

export interface AnalyticsAisleRankingCardsProps {
  rows: readonly AisleIssueRow[];
  costByAisle: ReadonlyMap<string, { total_cost?: number | null; total_counted_quantity?: number | null; cost_per_counted_unit?: number | null }>;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  emptyText: string;
}

export function AnalyticsAisleRankingCards({
  rows,
  costByAisle,
  isCostLoading,
  inventoryProcessingModeById,
  onOpenAisleDrilldown,
  emptyText,
}: AnalyticsAisleRankingCardsProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-aisles-ranking-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box data-testid="analytics-aisles-ranking" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {rows.map((row) => {
        const cost = costByAisle.get(row.aisle_id);
        const eligibility = getCompareEligibility(inventoryProcessingModeById.get(row.inventory_id));
        const compareHref = eligibility.allowed
          ? pathToInventoryAnalyticsCompareMany(row.inventory_id, { aisleId: row.aisle_id })
          : '';

        return (
          <Paper
            key={`${row.inventory_id}-${row.aisle_id}`}
            variant="outlined"
            data-testid={`analytics-aisle-card-${row.aisle_id}`}
            sx={{ p: 1.5 }}
          >
            <Typography variant="body2" fontWeight={700}>
              {row.aisle_code}
              <Typography component="span" variant="body2" color="text.secondary" fontWeight={400}>
                {' · '}
                {row.inventory_name}
              </Typography>
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25, mb: 1 }}>
              {t('analyticsDashboard.visual.attentionReviewRequired', { count: row.needs_review_count })}
              {row.most_common_issue
                ? ` · ${t('analyticsDashboard.visual.attentionPrimaryIssue', { issue: row.most_common_issue })}`
                : ''}
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
                {t('analyticsDashboard.costs.totalCost')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.total_cost, 'cost', t)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('analyticsDashboard.costs.totalQuantity')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.total_counted_quantity, 'quantity', t)}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ gridColumn: '1 / -1' }}>
                {t('analyticsDashboard.costs.costPerUnit')}:{' '}
                {formatCostCellWithLoading(isCostLoading, cost?.cost_per_counted_unit, 'costPerUnit', t)}
              </Typography>
            </Box>
            <AnalyticsEntityActionRow
              viewDetailLabel={t('analyticsDashboard.aisles.viewPositions')}
              viewDetailHref={pathToAislePositions(row.inventory_id, row.aisle_id)}
              viewDetailTestId={`aisle-view-positions-${row.aisle_id}`}
              analyticsLabel={t('analyticsDashboard.aisles.openAnalytics')}
              onAnalyticsClick={() => onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
              analyticsTestId={`aisle-drilldown-${row.aisle_id}`}
              compareLabel={t('analyticsDashboard.aisles.compareRuns')}
              compareHref={compareHref}
              compareDisabled={!eligibility.allowed}
              compareTooltip={eligibility.allowed ? '' : t(compareEligibilityTooltipKey(eligibility.reason))}
              compareTestId={`aisle-compare-${row.aisle_id}`}
            />
          </Paper>
        );
      })}
    </Box>
  );
}
