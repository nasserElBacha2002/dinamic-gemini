import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { AnalyticsCostSummaryResponse } from '../../../../api/types';
import { pathToAislePositions, pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../../constants/appRoutes';
import { useAisleJobsList } from '../../../../hooks';
import { formatDate } from '../../../../utils/formatDate';
import { getJobStatusLabel } from '../../../../utils/jobStatus';
import type { useAnalyticsDashboard } from '../../../analytics/hooks';
import { AnalyticsCostWarningsBlock } from '../AnalyticsCostWarningsBlock';
import {
  buildAisleDrilldownKpis,
  buildDrilldownWarnings,
  findAisleIssueRow,
  getCompareEligibilityForInventory,
  lookupAisleCost,
  mapJobsForDrilldownTable,
  processingModeLabel,
} from '../../adapters/analyticsDrilldownViewModel';
import { DrilldownActionBar } from './DrilldownActionBar';
import { DrilldownKpiGrid } from './DrilldownKpiGrid';
import { LoadingBlock } from '../../../../components/ui';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AisleDrilldownPanelProps {
  inventoryId: string;
  aisleId: string;
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  processingMode?: string;
}

export function AisleDrilldownPanel({
  inventoryId,
  aisleId,
  analytics,
  costSummary,
  isCostLoading,
  inventoryProcessingModeById,
  processingMode,
}: AisleDrilldownPanelProps) {
  const { t } = useTranslation();
  const aisle = findAisleIssueRow(analytics.aisleIssues?.items, inventoryId, aisleId);
  const costRow = lookupAisleCost(costSummary, aisleId);
  const warnings = useMemo(() => buildDrilldownWarnings(costSummary, t), [costSummary, t]);
  const compareEligibility = getCompareEligibilityForInventory(inventoryProcessingModeById, inventoryId);
  const compareHref = pathToInventoryAnalyticsCompareMany(inventoryId, { aisleId });

  const jobsQuery = useAisleJobsList(inventoryId, aisleId, { enabled: true, limit: 20 });

  const kpis = useMemo(
    () => buildAisleDrilldownKpis(aisle, costRow, t, isCostLoading),
    [aisle, costRow, t, isCostLoading]
  );

  const jobRows = useMemo(
    () => mapJobsForDrilldownTable(jobsQuery.data?.jobs ?? [], t),
    [jobsQuery.data?.jobs, t]
  );

  if (!aisle && !costRow) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-drilldown-aisle-empty">
        {t('analyticsDashboard.drilldown.noAisleData')}
      </Typography>
    );
  }

  return (
    <Box data-testid="analytics-drilldown-aisle-panel">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.aisleMeta', {
          inventory: aisle?.inventory_name ?? inventoryId,
          mode: processingModeLabel(processingMode, t),
        })}
      </Typography>

      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        {t('analyticsDashboard.drilldown.notCorrectionsHelper')}
      </Alert>

      {warnings.length > 0 ? (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            {t('analyticsDashboard.drilldown.costWarningsTitle')}
          </Typography>
          <AnalyticsCostWarningsBlock warnings={warnings} compact />
        </Box>
      ) : null}

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.costSummary')}
      </Typography>
      <DrilldownKpiGrid cards={kpis} isLoading={isCostLoading} data-testid="analytics-drilldown-aisle-kpis" />

      <Box sx={{ mt: 2, mb: 2 }}>
        <DrilldownActionBar
          compareEligibility={compareEligibility}
          compareHref={compareHref}
          primaryActions={[
            {
              id: 'open-positions',
              label: t('analyticsDashboard.drilldown.openAislePositions'),
              href: pathToAislePositions(inventoryId, aisleId),
              testId: 'analytics-drilldown-open-positions',
            },
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
        {t('analyticsDashboard.drilldown.qualitySummary')}
      </Typography>
      <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
        <Typography variant="body2">
          {t('analyticsDashboard.drilldown.reviewRequired')}: {aisle?.needs_review_count ?? '—'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('analyticsDashboard.drilldown.primaryIssue')}: {aisle?.most_common_issue ?? '—'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('analytics.column_unidentified_product')}: {aisle?.unidentified_product_count ?? 0}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('analytics.column_invalid_traceability')}: {aisle?.invalid_traceability_count ?? 0}
        </Typography>
      </Paper>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.jobsSummary')}
      </Typography>
      {jobsQuery.isLoading ? (
        <Box data-testid="analytics-drilldown-jobs-loading">
          <LoadingBlock message={t('analyticsDashboard.drilldown.loadingJobs')} />
        </Box>
      ) : jobRows.length === 0 ? (
        <Typography variant="body2" color="text.secondary" data-testid="analytics-drilldown-jobs-empty">
          {t('analyticsDashboard.drilldown.noJobs')}
        </Typography>
      ) : (
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-drilldown-jobs-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('analyticsDashboard.drilldown.jobColumn')}</TableCell>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell>{t('analyticsDashboard.drilldown.statusColumn')}</TableCell>
                <TableCell>{t('analyticsDashboard.drilldown.startedColumn')}</TableCell>
                <TableCell>{t('analyticsDashboard.drilldown.finishedColumn')}</TableCell>
                <TableCell align="right">{t('analyticsDashboard.drilldown.durationColumn')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {jobRows.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>{job.id.slice(0, 8)}</TableCell>
                  <TableCell>{job.provider}</TableCell>
                  <TableCell>{job.model}</TableCell>
                  <TableCell>{getJobStatusLabel(job.status)}</TableCell>
                  <TableCell>{formatDate(job.startedAt)}</TableCell>
                  <TableCell>{job.finishedAt === '—' ? '—' : formatDate(job.finishedAt)}</TableCell>
                  <TableCell align="right">{job.duration}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  );
}
