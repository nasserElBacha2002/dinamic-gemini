import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { AnalyticsKpiGrid } from './AnalyticsKpiGrid';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { MetricUnavailableState } from './MetricUnavailableState';
import { AnalyticsCostWarningsBlock } from './AnalyticsCostWarningsBlock';
import { AnalyticsCostVisualSection } from './AnalyticsCostVisualSection';
import {
  buildCostExecutiveKpis,
  buildCostWarnings,
  captureStatusLabel,
  costSummaryEmptyMessage,
  formatCostCell,
  formatProviderUnitCost,
  getCostSummaryEmptyKind,
  hasCostData,
} from '../adapters/analyticsCostViewModel';
import type { AnalyticsDrilldownHandlers } from '../types';

export interface AnalyticsCostsTabProps {
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isLoading: boolean;
  isError: boolean;
  onGoToCompare: () => void;
  drilldown: AnalyticsDrilldownHandlers;
}

function CompareCostsSection({ onGoToCompare }: { onGoToCompare: () => void }) {
  const { t } = useTranslation();
  return (
    <AnalyticsSectionCard title={t('analyticsDashboard.costs.perCompareSectionTitle')}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('analyticsDashboard.costs.compareAvailableDescription')}
      </Typography>
      <Button variant="outlined" onClick={onGoToCompare} data-testid="analytics-costs-go-compare">
        {t('analyticsDashboard.costs.goToCompare')}
      </Button>
    </AnalyticsSectionCard>
  );
}

export function AnalyticsCostsTab({
  costSummary,
  isLoading,
  isError,
  onGoToCompare,
  drilldown,
}: AnalyticsCostsTabProps) {
  const { t } = useTranslation();
  const executiveKpis = useMemo(() => buildCostExecutiveKpis(costSummary, t), [costSummary, t]);
  const warnings = useMemo(() => buildCostWarnings(costSummary, t), [costSummary, t]);
  const emptyKind = useMemo(() => getCostSummaryEmptyKind(costSummary), [costSummary]);

  if (isError) {
    return (
      <Box data-testid="analytics-costs-tab">
        <MetricUnavailableState
          title={t('analyticsDashboard.costs.loadError')}
          description={t('analyticsDashboard.costs.loadErrorDetail')}
        />
        <CompareCostsSection onGoToCompare={onGoToCompare} />
      </Box>
    );
  }

  const showEmpty = !isLoading && emptyKind != null;

  return (
    <Box data-testid="analytics-costs-tab">
      {showEmpty ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="analytics-costs-empty">
          {costSummaryEmptyMessage(emptyKind, t)}
        </Typography>
      ) : (
        <>
          <AnalyticsCostWarningsBlock warnings={warnings} />

          <AnalyticsSectionCard title={t('analyticsDashboard.costs.executiveSummaryTitle')}>
            <AnalyticsKpiGrid
              cards={executiveKpis}
              isLoading={isLoading}
              hasData={hasCostData(costSummary)}
              skeletonCount={10}
            />
          </AnalyticsSectionCard>

          <AnalyticsSectionCard title={t('analyticsDashboard.visual.costSnapshot')}>
            <AnalyticsCostVisualSection costSummary={costSummary} isLoading={isLoading} />
          </AnalyticsSectionCard>

          <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
            {t('analyticsDashboard.visual.drilldownTables')}
          </Typography>

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
                    <TableCell align="right">{t('analyticsDashboard.costs.avgExecutionTime')}</TableCell>
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
                          {formatCostCell(row.average_execution_time_seconds, 'duration', t)}
                        </TableCell>
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
                    <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.jobsWithCost')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalQuantity')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalExecutionTime')}</TableCell>
                    <TableCell>{t('common.actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(costSummary?.by_inventory ?? []).map((row) => (
                    <TableRow key={row.inventory_id}>
                      <TableCell>{row.inventory_name ?? row.inventory_id}</TableCell>
                      <TableCell align="right">{row.jobs_total}</TableCell>
                      <TableCell align="right">{row.jobs_with_cost}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_counted_quantity, 'quantity', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_execution_time_seconds, 'duration', t)}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          onClick={() => drilldown.onOpenInventoryDrilldown(row.inventory_id)}
                          data-testid={`cost-drilldown-inventory-${row.inventory_id}`}
                        >
                          {t('analyticsDashboard.drilldown.openAnalytics')}
                        </Button>
                      </TableCell>
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
                    <TableCell>{t('analytics.column_inventory')}</TableCell>
                    <TableCell>{t('common.aisle')}</TableCell>
                    <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.jobsWithCost')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalCost')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalQuantity')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.costPerUnit')}</TableCell>
                    <TableCell align="right">{t('analyticsDashboard.costs.totalExecutionTime')}</TableCell>
                    <TableCell>{t('common.actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(costSummary?.by_aisle ?? []).map((row) => (
                    <TableRow key={row.aisle_id}>
                      <TableCell>{row.inventory_name ?? row.inventory_id}</TableCell>
                      <TableCell>{row.aisle_code ?? row.aisle_id}</TableCell>
                      <TableCell align="right">{row.jobs_total}</TableCell>
                      <TableCell align="right">{row.jobs_with_cost}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_cost, 'cost', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_counted_quantity, 'quantity', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.cost_per_counted_unit, 'costPerUnit', t)}</TableCell>
                      <TableCell align="right">{formatCostCell(row.total_execution_time_seconds, 'duration', t)}</TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          onClick={() => drilldown.onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
                          data-testid={`cost-drilldown-aisle-${row.aisle_id}`}
                        >
                          {t('analyticsDashboard.drilldown.openAnalytics')}
                        </Button>
                      </TableCell>
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
        </>
      )}

      <CompareCostsSection onGoToCompare={onGoToCompare} />
    </Box>
  );
}
