import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { Box, Button, Tooltip, Typography } from '@mui/material';
import { pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { DataTable, type DataTableColumn } from '../../../components/ui';
import { formatDate } from '../../../utils/formatDate';
import { formatAvgProcessingMinutes, formatPct, paginateRows } from '../../analytics/adapters/metricsFormatters';
import { sortInventoryRows } from '../../analytics/adapters/metricsViewModel';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { InventoryPerformanceRow } from '../../analytics/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import {
  buildCostByInventoryLookup,
  buildCostWarnings,
  formatCostCellWithLoading,
} from '../adapters/analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsInventoriesTabProps {
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
}

export function AnalyticsInventoriesTab({
  analytics,
  costSummary,
  isLoading,
  isCostLoading,
  inventoryProcessingModeById,
}: AnalyticsInventoriesTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [sortBy, setSortBy] = useState('auto_accept');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const hasUnidentified = analytics.summary?.unidentified_product_rate != null;
  const costByInventory = useMemo(() => buildCostByInventoryLookup(costSummary), [costSummary]);
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);

  const rowsSorted = useMemo(
    () => sortInventoryRows(analytics.inventoryPerformance?.items ?? [], sortBy, sortDir),
    [analytics.inventoryPerformance?.items, sortBy, sortDir]
  );
  const rowsPaged = useMemo(() => paginateRows(rowsSorted, page, pageSize), [rowsSorted, page, pageSize]);

  const columns = useMemo<DataTableColumn<InventoryPerformanceRow>[]>(
    () => [
      {
        id: 'name',
        label: t('analytics.column_inventory'),
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={pathToInventory(r.inventory_id)}
            variant="body2"
            fontWeight={600}
            color="primary"
            sx={{ textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            {r.inventory_name}
          </Typography>
        ),
      },
      {
        id: 'created',
        label: t('common.created'),
        cell: (r) => formatDate(r.inventory_created_at),
      },
      {
        id: 'positions',
        label: t('analytics.column_positions'),
        align: 'right',
        cell: (r) => r.positions_count ?? r.total_positions,
      },
      {
        id: 'processed',
        label: t('analytics.column_processed'),
        align: 'right',
        cell: (r) => r.processed_count ?? r.processed_positions,
      },
      {
        id: 'auto_accept',
        label: t('analytics.column_auto_accept'),
        align: 'right',
        cell: (r) => formatPct(r.auto_acceptance_rate),
      },
      ...(hasUnidentified
        ? [
            {
              id: 'unidentified_product',
              label: t('analytics.column_unidentified_product'),
              align: 'right' as const,
              cell: (r: InventoryPerformanceRow) => formatPct(r.unidentified_product_rate),
            },
          ]
        : []),
      {
        id: 'avg_processing',
        label: t('analytics.column_avg_processing'),
        align: 'right',
        cell: (r) => formatAvgProcessingMinutes(r.average_processing_time_minutes, null),
      },
      {
        id: 'total_cost',
        label: t('analyticsDashboard.costs.totalCost'),
        align: 'right',
        sortable: false,
        cell: (r) =>
          formatCostCellWithLoading(
            isCostLoading,
            costByInventory.get(r.inventory_id)?.total_cost,
            'cost',
            t
          ),
      },
      {
        id: 'counted_qty',
        label: t('analyticsDashboard.costs.totalQuantity'),
        align: 'right',
        sortable: false,
        cell: (r) =>
          formatCostCellWithLoading(
            isCostLoading,
            costByInventory.get(r.inventory_id)?.total_counted_quantity,
            'quantity',
            t
          ),
      },
      {
        id: 'cost_per_unit',
        label: t('analyticsDashboard.costs.costPerUnit'),
        align: 'right',
        sortable: false,
        cell: (r) =>
          formatCostCellWithLoading(
            isCostLoading,
            costByInventory.get(r.inventory_id)?.cost_per_counted_unit,
            'costPerUnit',
            t
          ),
      },
      {
        id: 'actions',
        label: t('common.actions'),
        cell: (r) => {
          const eligibility = getCompareEligibility(inventoryProcessingModeById.get(r.inventory_id));
          const href = eligibility.allowed ? pathToInventoryAnalyticsCompareMany(r.inventory_id) : '';
          const tooltip = eligibility.allowed ? '' : t(compareEligibilityTooltipKey(eligibility.reason));
          return (
            <span style={{ display: 'inline-flex', gap: 8, flexWrap: 'wrap' }}>
              <Button size="small" component={RouterLink} to={pathToInventory(r.inventory_id)}>
                {t('analyticsDashboard.inventories.viewDetail')}
              </Button>
              <Tooltip title={tooltip}>
                <span>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={!eligibility.allowed}
                    data-testid={`inventory-compare-${r.inventory_id}`}
                    onClick={() => href && navigate(href)}
                  >
                    {t('analyticsDashboard.inventories.compareRuns')}
                  </Button>
                </span>
              </Tooltip>
            </span>
          );
        },
      },
    ],
    [costByInventory, hasUnidentified, inventoryProcessingModeById, isCostLoading, navigate, t]
  );

  return (
    <Box data-testid="analytics-inventories-table">
      {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {t('analyticsDashboard.costs.columnsContext')}
      </Typography>
      <DataTable<InventoryPerformanceRow>
        rows={rowsPaged}
        rowKey={(r) => r.inventory_id}
        columns={columns}
        loading={isLoading}
        size="small"
        pagination={{
          page,
          pageSize,
          totalItems: rowsSorted.length,
          onPageChange: setPage,
          onPageSizeChange: setPageSize,
        }}
        sort={{
          sortBy,
          sortDir,
          onSortChange: (nextSortBy, nextSortDir) => {
            setSortBy(nextSortBy);
            setSortDir(nextSortDir);
            setPage(1);
          },
        }}
        emptyState={{ message: t('analytics.empty_inventory_performance') }}
      />
    </Box>
  );
}
