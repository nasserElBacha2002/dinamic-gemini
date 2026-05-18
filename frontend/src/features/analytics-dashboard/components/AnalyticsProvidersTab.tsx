import { useTranslation } from 'react-i18next';
import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { MetricUnavailableCards } from './MetricUnavailableState';

export interface AnalyticsProvidersTabProps {
  observability: ObservabilityMetricsResponse | null | undefined;
}

function pctLabel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

export function AnalyticsProvidersTab({ observability }: AnalyticsProvidersTabProps) {
  const { t } = useTranslation();
  const rows = observability?.by_provider_model ?? [];

  return (
    <>
      <AnalyticsSectionCard
        title={t('analyticsDashboard.providers.sectionTitle')}
        grainLabel={t('analyticsDashboard.grain_runs')}
        subtitle={t('analyticsDashboard.compare.notRecommendation')}
      >
        <Paper variant="outlined">
          <Table size="small" data-testid="analytics-providers-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('observability.metrics.colProvider')}</TableCell>
                <TableCell>{t('observability.metrics.colModel')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colSucceeded')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colFailed')}</TableCell>
                <TableCell align="right">{t('observability.metrics.colFailureRate')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, idx) => (
                <TableRow key={`${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`}>
                  <TableCell>{row.provider_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell>{row.model_name ?? t('observability.metrics.unknownId')}</TableCell>
                  <TableCell align="right">{row.runs_total}</TableCell>
                  <TableCell align="right">{row.runs_succeeded}</TableCell>
                  <TableCell align="right">{row.runs_failed}</TableCell>
                  <TableCell align="right">{pctLabel(row.failure_rate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
        {!rows.length ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('observability.metrics.empty')}
          </Typography>
        ) : null}
      </AnalyticsSectionCard>

      <AnalyticsSectionCard title={t('analyticsDashboard.providers.costUnavailable')}>
        <MetricUnavailableCards
          cards={[
            {
              label: t('analyticsDashboard.providers.costUnavailable'),
              value: t('analyticsDashboard.costs.unavailableCard'),
              description: t('analyticsDashboard.costs.unavailableExplain'),
            },
          ]}
        />
      </AnalyticsSectionCard>
    </>
  );
}
