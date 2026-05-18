import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { Box, Button, Tooltip, Typography } from '@mui/material';
import { pathToAislePositions, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { DataTable, sortDataTableRows, type DataTableColumn } from '../../../components/ui';
import { paginateRows } from '../../analytics/adapters/metricsFormatters';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { AisleIssueRow } from '../../analytics/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import {
  buildCostByAisleLookup,
  buildCostWarnings,
  formatCostCellWithLoading,
} from '../adapters/analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsAislesTabProps {
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
}

export function AnalyticsAislesTab({
  analytics,
  costSummary,
  isLoading,
  isCostLoading,
  inventoryProcessingModeById,
}: AnalyticsAislesTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [sortBy, setSortBy] = useState('pending');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const costByAisle = useMemo(() => buildCostByAisleLookup(costSummary), [costSummary]);
  const costWarnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);

  const columns = useMemo<DataTableColumn<AisleIssueRow>[]>(
    () => [
      {
        id: 'aisle',
        label: t('common.aisle'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.aisle_code,
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={pathToAislePositions(r.inventory_id, r.aisle_id)}
            variant="body2"
            fontWeight={600}
            color="primary"
            sx={{ textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            {r.aisle_code}
          </Typography>
        ),
      },
      {
        id: 'inventory',
        label: t('analytics.column_inventory'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.inventory_name,
        cell: (r) => r.inventory_name,
      },
      {
        id: 'total',
        label: t('analytics.column_total'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (r) => r.total_results,
        cell: (r) => r.total_results,
      },
      {
        id: 'pending',
        label: t('analytics.column_pending'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (r) => r.needs_review_count,
        cell: (r) => r.needs_review_count,
      },
      {
        id: 'issue',
        label: t('analyticsDashboard.aisles.attentionStatus'),
        cell: (r) => r.most_common_issue ?? '—',
      },
      {
        id: 'total_cost',
        label: t('analyticsDashboard.costs.totalCost'),
        align: 'right',
        sortable: false,
        cell: (r) =>
          formatCostCellWithLoading(isCostLoading, costByAisle.get(r.aisle_id)?.total_cost, 'cost', t),
      },
      {
        id: 'counted_qty',
        label: t('analyticsDashboard.costs.totalQuantity'),
        align: 'right',
        sortable: false,
        cell: (r) =>
          formatCostCellWithLoading(
            isCostLoading,
            costByAisle.get(r.aisle_id)?.total_counted_quantity,
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
            costByAisle.get(r.aisle_id)?.cost_per_counted_unit,
            'costPerUnit',
            t
          ),
      },
      {
        id: 'actions',
        label: t('common.actions'),
        cell: (r) => {
          const eligibility = getCompareEligibility(inventoryProcessingModeById.get(r.inventory_id));
          const href = eligibility.allowed
            ? pathToInventoryAnalyticsCompareMany(r.inventory_id, { aisleId: r.aisle_id })
            : '';
          const tooltip = eligibility.allowed ? '' : t(compareEligibilityTooltipKey(eligibility.reason));
          return (
            <Tooltip title={tooltip}>
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!eligibility.allowed}
                  data-testid={`aisle-compare-${r.aisle_id}`}
                  onClick={() => href && navigate(href)}
                >
                  {t('analyticsDashboard.aisles.compareRuns')}
                </Button>
              </span>
            </Tooltip>
          );
        },
      },
    ],
    [costByAisle, inventoryProcessingModeById, isCostLoading, navigate, t]
  );

  const rowsSorted = useMemo(
    () => sortDataTableRows(analytics.aisleIssues?.items ?? [], columns, sortBy, sortDir),
    [analytics.aisleIssues?.items, columns, sortBy, sortDir]
  );
  const rowsPaged = useMemo(() => paginateRows(rowsSorted, page, pageSize), [rowsSorted, page, pageSize]);

  return (
    <Box data-testid="analytics-aisles-table">
      {costWarnings.length > 0 ? <AnalyticsCostWarningsBlock warnings={costWarnings} compact /> : null}
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {t('analyticsDashboard.costs.columnsContext')}
      </Typography>
      <DataTable<AisleIssueRow>
        rows={rowsPaged}
        rowKey={(r) => `${r.inventory_id}-${r.aisle_id}`}
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
        emptyState={{ message: t('analytics.empty_aisle_metrics') }}
      />
    </Box>
  );
}
