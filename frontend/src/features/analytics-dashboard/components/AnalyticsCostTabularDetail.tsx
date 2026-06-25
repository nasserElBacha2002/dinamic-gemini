import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Tooltip } from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { DataTable, type DataTableColumn } from '../../../components/ui';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import {
  captureStatusLabel,
  formatCostCell,
  formatProviderUnitCost,
} from '../adapters/analyticsCostViewModel';

type ProviderModelRow = NonNullable<AnalyticsCostSummaryResponse['by_provider_model']>[number];
type InventoryCostRow = NonNullable<AnalyticsCostSummaryResponse['by_inventory']>[number];
type AisleCostRow = NonNullable<AnalyticsCostSummaryResponse['by_aisle']>[number];
type CaptureStatusRow = NonNullable<AnalyticsCostSummaryResponse['by_capture_status']>[number];

export interface AnalyticsCostTabularDetailProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
}

export function AnalyticsCostTabularDetail({ costSummary }: AnalyticsCostTabularDetailProps) {
  const { t } = useTranslation();

  const providerColumns = useMemo((): DataTableColumn<ProviderModelRow>[] => {
    const unknown = t('observability.metrics.unknownId');
    return [
      {
        id: 'provider',
        label: t('observability.metrics.colProvider'),
        cell: (row) => row.provider_name ?? unknown,
      },
      {
        id: 'model',
        label: t('observability.metrics.colModel'),
        cell: (row) => row.model_name ?? unknown,
      },
      {
        id: 'jobs_total',
        label: t('observability.metrics.colRuns'),
        align: 'right',
        cell: (row) => row.jobs_total,
      },
      {
        id: 'jobs_with_cost',
        label: t('analyticsDashboard.costs.jobsWithCost'),
        align: 'right',
        cell: (row) => row.jobs_with_cost,
      },
      {
        id: 'total_cost',
        label: t('analyticsDashboard.costs.totalCost'),
        align: 'right',
        cell: (row) => formatCostCell(row.total_cost, 'cost', t),
      },
      {
        id: 'cost_per_unit',
        label: t('analyticsDashboard.costs.costPerUnit'),
        align: 'right',
        cell: (row) => {
          const unit = formatProviderUnitCost(row.cost_per_counted_unit, t);
          return unit.helper ? (
            <Tooltip title={unit.helper}>
              <span>{unit.display}</span>
            </Tooltip>
          ) : (
            unit.display
          );
        },
      },
    ];
  }, [t]);

  const inventoryColumns = useMemo((): DataTableColumn<InventoryCostRow>[] => [
    {
      id: 'inventory',
      label: t('analytics.column_inventory'),
      cell: (row) => row.inventory_name ?? row.inventory_id,
    },
    {
      id: 'total_cost',
      label: t('analyticsDashboard.costs.totalCost'),
      align: 'right',
      cell: (row) => formatCostCell(row.total_cost, 'cost', t),
    },
    {
      id: 'total_quantity',
      label: t('analyticsDashboard.costs.totalQuantity'),
      align: 'right',
      cell: (row) => formatCostCell(row.total_counted_quantity, 'quantity', t),
    },
    {
      id: 'cost_per_unit',
      label: t('analyticsDashboard.costs.costPerUnit'),
      align: 'right',
      cell: (row) => formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t),
    },
  ], [t]);

  const aisleColumns = useMemo((): DataTableColumn<AisleCostRow>[] => [
    {
      id: 'aisle',
      label: t('common.aisle'),
      cell: (row) => row.aisle_code ?? row.aisle_id,
    },
    {
      id: 'inventory',
      label: t('analytics.column_inventory'),
      cell: (row) => row.inventory_name ?? row.inventory_id,
    },
    {
      id: 'total_cost',
      label: t('analyticsDashboard.costs.totalCost'),
      align: 'right',
      cell: (row) => formatCostCell(row.total_cost, 'cost', t),
    },
    {
      id: 'cost_per_unit',
      label: t('analyticsDashboard.costs.costPerUnit'),
      align: 'right',
      cell: (row) => formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t),
    },
  ], [t]);

  const captureColumns = useMemo((): DataTableColumn<CaptureStatusRow>[] => [
    {
      id: 'capture_status',
      label: t('analyticsDashboard.costs.captureStatusColumn'),
      cell: (row) => captureStatusLabel(row.capture_status, t),
    },
    {
      id: 'jobs_total',
      label: t('observability.metrics.colRuns'),
      align: 'right',
      cell: (row) => row.jobs_total,
    },
    {
      id: 'total_cost',
      label: t('analyticsDashboard.costs.totalCost'),
      align: 'right',
      cell: (row) => formatCostCell(row.total_cost, 'cost', t),
    },
  ], [t]);

  const providerRows = costSummary?.by_provider_model ?? [];
  const inventoryRows = costSummary?.by_inventory ?? [];
  const aisleRows = costSummary?.by_aisle ?? [];
  const captureRows = costSummary?.by_capture_status ?? [];

  return (
    <Box data-testid="analytics-cost-tabular-detail">
      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byProviderModelTitle')}>
        <DataTable
          testId="analytics-cost-by-provider-table"
          rows={providerRows}
          rowKey={(row) => `${row.provider_name ?? ''}-${row.model_name ?? ''}-${row.jobs_total}`}
          columns={providerColumns}
          stickyHeader={false}
        />
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byInventoryTitle')}>
        <DataTable
          testId="analytics-cost-by-inventory-table"
          rows={inventoryRows}
          rowKey={(row) => row.inventory_id}
          columns={inventoryColumns}
          stickyHeader={false}
        />
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byAisleTitle')}>
        <DataTable
          testId="analytics-cost-by-aisle-table"
          rows={aisleRows}
          rowKey={(row) => row.aisle_id}
          columns={aisleColumns}
          stickyHeader={false}
        />
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byCaptureStatusTitle')}>
        <DataTable
          testId="analytics-cost-by-capture-table"
          rows={captureRows}
          rowKey={(row) => row.capture_status}
          columns={captureColumns}
          stickyHeader={false}
        />
      </AnalyticsSectionCard>
    </Box>
  );
}
