import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { AnalyticsCostSummaryResponse, Inventory } from '../../../../api/types';
import { pathToAislePositions, pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../../constants/appRoutes';
import { useInventoryMetrics } from '../../../../hooks';
import { formatDate } from '../../../../utils/formatDate';
import type { useAnalyticsDashboard } from '../../../analytics/hooks';
import { DataTable, type DataTableColumn } from '../../../../components/ui';
import { useTableState } from '../../../../hooks';
import { DrilldownScopeWarnings } from './DrilldownScopeWarnings';
import { HorizontalBarChart } from '../charts/HorizontalBarChart';
import { buildCostByAisleChartData } from '../../adapters/analyticsChartDatasets';
import {
  buildAisleContributionRows,
  buildDrilldownWarnings,
  buildInventoryDrilldownKpis,
  filterCostAislesForInventory,
  findInventoryPerformanceRow,
  getCompareEligibilityForInventory,
  lookupInventoryCost,
  processingModeLabel,
  type AisleContributionRow,
} from '../../adapters/analyticsDrilldownViewModel';
import { formatCostCell } from '../../adapters/analyticsCostViewModel';
import { DrilldownActionBar } from './DrilldownActionBar';
import { DrilldownKpiGrid } from './DrilldownKpiGrid';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface InventoryDrilldownPanelProps {
  inventoryId: string;
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isCostLoading: boolean;
  inventoryMeta?: Inventory;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
}

export function InventoryDrilldownPanel({
  inventoryId,
  analytics,
  costSummary,
  isCostLoading,
  inventoryMeta,
  inventoryProcessingModeById,
  onOpenAisleDrilldown,
}: InventoryDrilldownPanelProps) {
  const { t } = useTranslation();
  const { page, pageSize, setPage, setPageSize } = useTableState();
  const performance = findInventoryPerformanceRow(analytics.inventoryPerformance?.items, inventoryId);
  const costRow = lookupInventoryCost(costSummary, inventoryId);
  const aisleCount = (analytics.aisleIssues?.items ?? []).filter((r) => r.inventory_id === inventoryId).length;
  const warnings = useMemo(() => buildDrilldownWarnings(costSummary, t), [costSummary, t]);
  const compareEligibility = getCompareEligibilityForInventory(inventoryProcessingModeById, inventoryId);
  const compareHref = pathToInventoryAnalyticsCompareMany(inventoryId);

  const metricsQuery = useInventoryMetrics(inventoryId, { enabled: true });

  const kpis = useMemo(
    () => buildInventoryDrilldownKpis(performance, costRow, aisleCount, t, isCostLoading),
    [performance, costRow, aisleCount, t, isCostLoading]
  );

  const contributionRows = useMemo(
    () => buildAisleContributionRows(analytics.aisleIssues?.items ?? [], costSummary, inventoryId),
    [analytics.aisleIssues?.items, costSummary, inventoryId]
  );

  const costAislesChart = useMemo(() => {
    const byAisle = filterCostAislesForInventory(costSummary, inventoryId);
    if (!byAisle.length || !costSummary) return [];
    return buildCostByAisleChartData({
      ...costSummary,
      by_provider_model: [],
      by_inventory: [],
      by_aisle: byAisle,
      by_capture_status: [],
      warnings: [],
    });
  }, [costSummary, inventoryId]);

  const emptyChart = t('analyticsDashboard.visual.emptyChart');

  const aisleColumns = useMemo((): DataTableColumn<AisleContributionRow>[] => [
    {
      id: 'aisle',
      label: t('common.aisle'),
      cell: (row) => row.aisleCode,
    },
    {
      id: 'needs_review',
      label: t('analyticsDashboard.drilldown.reviewRequired'),
      align: 'right',
      cell: (row) => row.needsReviewCount,
    },
    {
      id: 'total_cost',
      label: t('analyticsDashboard.costs.totalCost'),
      align: 'right',
      cell: (row) => formatCostCell(row.totalCost, 'cost', t),
    },
    {
      id: 'cost_per_unit',
      label: t('analyticsDashboard.costs.costPerUnit'),
      align: 'right',
      cell: (row) => formatCostCell(row.costPerUnit, 'costPerUnit', t),
    },
    {
      id: 'actions',
      label: t('common.actions'),
      cell: (row) => {
        const rowEligibility = getCompareEligibilityForInventory(
          inventoryProcessingModeById,
          row.inventoryId
        );
        return (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            <Button
              size="small"
              component={RouterLink}
              to={pathToAislePositions(row.inventoryId, row.aisleId)}
            >
              {t('analyticsDashboard.drilldown.openAislePositions')}
            </Button>
            <Button
              size="small"
              onClick={() => onOpenAisleDrilldown(row.inventoryId, row.aisleId)}
              data-testid={`drilldown-aisle-open-${row.aisleId}`}
            >
              {t('analyticsDashboard.drilldown.openAnalytics')}
            </Button>
            <Button
              size="small"
              disabled={!rowEligibility.allowed}
              component={rowEligibility.allowed ? RouterLink : 'button'}
              to={
                rowEligibility.allowed
                  ? pathToInventoryAnalyticsCompareMany(row.inventoryId, { aisleId: row.aisleId })
                  : undefined
              }
            >
              {t('analyticsDashboard.drilldown.compareRuns')}
            </Button>
          </Box>
        );
      },
    },
  ], [inventoryProcessingModeById, onOpenAisleDrilldown, t]);

  const paginatedContributionRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return contributionRows.slice(start, start + pageSize);
  }, [contributionRows, page, pageSize]);

  if (!performance && !costRow) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-drilldown-inventory-empty">
        {t('analyticsDashboard.drilldown.noInventoryData')}
      </Typography>
    );
  }

  return (
    <Box data-testid="analytics-drilldown-inventory-panel">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.inventoryMeta', {
          id: inventoryId,
          created: performance?.inventory_created_at ? formatDate(performance.inventory_created_at) : '—',
          mode: processingModeLabel(inventoryMeta?.processing_mode, t),
        })}
      </Typography>

      <DrilldownScopeWarnings warnings={warnings} />

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.costSummary')}
      </Typography>
      <DrilldownKpiGrid cards={kpis} isLoading={isCostLoading} data-testid="analytics-drilldown-inventory-kpis" />

      <Box sx={{ mt: 2, mb: 2 }}>
        <DrilldownActionBar
          compareEligibility={compareEligibility}
          compareHref={compareHref}
          primaryActions={[
            {
              id: 'open-inventory',
              label: t('analyticsDashboard.drilldown.openInventory'),
              href: pathToInventory(inventoryId),
              testId: 'analytics-drilldown-open-inventory',
            },
          ]}
        />
      </Box>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.aisleContribution')}
      </Typography>
      {contributionRows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {emptyChart}
        </Typography>
      ) : (
        <DataTable
          testId="analytics-drilldown-inventory-aisles"
          rows={paginatedContributionRows}
          rowKey={(row) => row.aisleId}
          columns={aisleColumns}
          stickyHeader={false}
          pagination={{
            page,
            pageSize,
            totalItems: contributionRows.length,
            onPageChange: setPage,
            onPageSizeChange: setPageSize,
          }}
        />
      )}

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('analyticsDashboard.visual.topAislesByCost')}
      </Typography>
      <HorizontalBarChart
        data={costAislesChart}
        emptyText={emptyChart}
        ariaLabel={t('analyticsDashboard.visual.topAislesByCost')}
        data-testid="analytics-drilldown-inventory-cost-chart"
      />

      {metricsQuery.data ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
          {t('analyticsDashboard.drilldown.positionsReviewed', {
            reviewed: metricsQuery.data.total_reviewed_positions,
            total: metricsQuery.data.total_positions,
          })}
        </Typography>
      ) : null}
    </Box>
  );
}
