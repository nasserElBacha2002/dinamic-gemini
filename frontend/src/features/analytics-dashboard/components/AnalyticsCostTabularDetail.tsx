import { useTranslation } from 'react-i18next';
import { Box } from '@mui/material';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
} from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import {
  captureStatusLabel,
  formatCostCell,
  formatProviderUnitCost,
} from '../adapters/analyticsCostViewModel';
export interface AnalyticsCostTabularDetailProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
}

export function AnalyticsCostTabularDetail({ costSummary }: AnalyticsCostTabularDetailProps) {
  const { t } = useTranslation();

  return (
    <Box data-testid="analytics-cost-tabular-detail">
      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byProviderModelTitle')}>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-cost-by-provider-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.jobsWithCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(costSummary?.by_provider_model ?? []).map((row, idx) => {
                const unit = formatProviderUnitCost(row.cost_per_counted_unit, t);
                return (
                  <TableRow key={`${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}>
                    <TableCell>{row.provider_name ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell>{row.model_name ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell align="right">{row.jobs_total}</TableCell>
                    <TableCell align="right">{row.jobs_with_cost}</TableCell>
                    <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                    <TableCell align="right">
                      {unit.helper ? (
                        <Tooltip title={unit.helper}>
                          <span>{unit.display}</span>
                        </Tooltip>
                      ) : (
                        unit.display
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byInventoryTitle')}>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-cost-by-inventory-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('analytics.column_inventory')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalQuantity')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(costSummary?.by_inventory ?? []).map((row) => (
                <TableRow key={row.inventory_id}>
                  <TableCell>{row.inventory_name ?? row.inventory_id}</TableCell>
                  <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                  <TableCell align="right">{formatCostCell(row.total_counted_quantity, 'quantity', t)}</TableCell>
                  <TableCell align="right">{formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byAisleTitle')}>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-cost-by-aisle-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.aisle')}</TableCell>
                <TableCell>{t('analytics.column_inventory')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(costSummary?.by_aisle ?? []).map((row) => (
                <TableRow key={row.aisle_id}>
                  <TableCell>{row.aisle_code ?? row.aisle_id}</TableCell>
                  <TableCell>{row.inventory_name ?? row.inventory_id}</TableCell>
                  <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                  <TableCell align="right">{formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.costs.byCaptureStatusTitle')}>
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-cost-by-capture-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('analyticsDashboard.costs.captureStatusColumn')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(costSummary?.by_capture_status ?? []).map((row) => (
                <TableRow key={row.capture_status}>
                  <TableCell>{captureStatusLabel(row.capture_status, t)}</TableCell>
                  <TableCell align="right">{row.jobs_total}</TableCell>
                  <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </AnalyticsSectionCard>
    </Box>
  );
}
