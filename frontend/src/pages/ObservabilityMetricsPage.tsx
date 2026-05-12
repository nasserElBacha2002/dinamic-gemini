/**
 * Phase H5 — read-only operational metrics (Spanish UI via i18n).
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { PageHeader } from '../components/shell';
import { ErrorAlert } from '../components/ui';
import type { ObservabilityMetricsQueryParams } from '../api/observabilityApi';
import { ROUTE_OBSERVABILIDAD } from '../constants/appRoutes';
import { useObservabilityMetrics } from '../hooks/useObservabilityMetrics';
import { resolveApiErrorMessage } from '../utils/apiErrors';

function defaultRangeIso(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 30);
  const pad = (d: Date) => d.toISOString().slice(0, 10);
  return { from: `${pad(from)}T00:00:00.000Z`, to: `${pad(to)}T23:59:59.999Z` };
}

function pctLabel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

function KpiCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {title}
      </Typography>
      <Typography variant="h6" component="div">
        {value}
      </Typography>
    </Paper>
  );
}

export default function ObservabilityMetricsPage() {
  const { t } = useTranslation();
  const initial = useMemo(() => defaultRangeIso(), []);
  const [draft, setDraft] = useState({
    dateFrom: initial.from.slice(0, 10),
    dateTo: initial.to.slice(0, 10),
    clientId: '',
    clientSupplierId: '',
    providerName: '',
    modelName: '',
  });
  const [applied, setApplied] = useState<ObservabilityMetricsQueryParams>(() => ({
    from: initial.from,
    to: initial.to,
  }));

  const buildParams = useCallback((): ObservabilityMetricsQueryParams => {
    const from = `${draft.dateFrom}T00:00:00.000Z`;
    const to = `${draft.dateTo}T23:59:59.999Z`;
    return {
      from,
      to,
      clientId: draft.clientId.trim() || undefined,
      clientSupplierId: draft.clientSupplierId.trim() || undefined,
      providerName: draft.providerName.trim() || undefined,
      modelName: draft.modelName.trim() || undefined,
    };
  }, [draft]);

  const q = useObservabilityMetrics(applied);

  const onApply = () => {
    setApplied(buildParams());
  };

  const data = q.data;
  const totals = data?.totals;
  const dq = data?.data_quality;

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400, mx: 'auto' }}>
      <PageHeader
        title={t('observability.metrics.title')}
        subtitle={t('observability.metrics.subtitle')}
        breadcrumbs={[{ label: t('nav.observability'), to: ROUTE_OBSERVABILIDAD }]}
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.metrics.filtersTitle')}
        </Typography>
        <Grid container spacing={2} alignItems="flex-end">
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.dateFrom')}
              type="date"
              value={draft.dateFrom}
              onChange={(e) => setDraft((d) => ({ ...d, dateFrom: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.dateTo')}
              type="date"
              value={draft.dateTo}
              onChange={(e) => setDraft((d) => ({ ...d, dateTo: e.target.value }))}
              InputLabelProps={{ shrink: true }}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.clientId')}
              value={draft.clientId}
              onChange={(e) => setDraft((d) => ({ ...d, clientId: e.target.value }))}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.supplierId')}
              value={draft.clientSupplierId}
              onChange={(e) => setDraft((d) => ({ ...d, clientSupplierId: e.target.value }))}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.provider')}
              value={draft.providerName}
              onChange={(e) => setDraft((d) => ({ ...d, providerName: e.target.value }))}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label={t('observability.metrics.model')}
              value={draft.modelName}
              onChange={(e) => setDraft((d) => ({ ...d, modelName: e.target.value }))}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button variant="contained" onClick={onApply} disabled={q.isFetching}>
              {t('observability.metrics.applyFilters')}
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {q.isLoading ? (
        <Typography variant="body2" color="text.secondary">
          {t('observability.metrics.loading')}
        </Typography>
      ) : null}

      {q.isError ? (
        <ErrorAlert
          message={resolveApiErrorMessage(q.error, 'observability.metrics.loadError')}
          retryLabel={t('common.retry')}
          onRetry={() => {
            void q.refetch();
          }}
        />
      ) : null}

      {data && totals && totals.runs_total === 0 ? (
        <Alert severity="info">{t('observability.metrics.empty')}</Alert>
      ) : null}

      {data && totals && totals.runs_total > 0 ? (
        <Stack spacing={3}>
          {dq && dq.jobs_without_audit_snapshot > 0 ? (
            <Alert severity="warning">
              {t('observability.metrics.partialDataNote')}
            </Alert>
          ) : null}

          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiRuns')} value={totals.runs_total} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiSucceeded')} value={totals.runs_succeeded} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiFailed')} value={totals.runs_failed} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiFailureRate')} value={pctLabel(totals.failure_rate)} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiFallbacks')} value={totals.fallback_runs} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiMissingPrompt')} value={totals.missing_prompt_config_runs} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiMissingRef')} value={totals.missing_reference_runs} />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <KpiCard title={t('observability.metrics.kpiLegacy')} value={totals.legacy_runs} />
            </Grid>
          </Grid>

          {dq ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                {t('observability.metrics.dataQualityTitle')}
              </Typography>
              <Typography variant="body2">
                {t('observability.metrics.dataQualitySnapshot', { count: dq.jobs_with_audit_snapshot })}
              </Typography>
              <Typography variant="body2">
                {t('observability.metrics.dataQualityNoSnapshot', { count: dq.jobs_without_audit_snapshot })}
              </Typography>
              <Typography variant="body2">
                {t('observability.metrics.dataQualityMissingMeta', { count: dq.jobs_with_missing_metadata })}
              </Typography>
              <Typography variant="body2">
                {t('observability.metrics.dataQualityArtifact', { count: dq.artifact_dependent_jobs })}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t('observability.metrics.dataQualityHelper')}
              </Typography>
            </Paper>
          ) : null}

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              {t('observability.metrics.tableClients')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('observability.metrics.colClient')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colSucceeded')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colFailed')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colFailureRate')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.by_client.map((row) => (
                  <TableRow key={row.client_id ?? '__none__'}>
                    <TableCell>{row.client_id ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell align="right">{row.runs_total}</TableCell>
                    <TableCell align="right">{row.runs_succeeded}</TableCell>
                    <TableCell align="right">{row.runs_failed}</TableCell>
                    <TableCell align="right">{pctLabel(row.failure_rate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              {t('observability.metrics.tableSuppliers')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('observability.metrics.colSupplier')}</TableCell>
                  <TableCell>{t('observability.metrics.colClient')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colRuns')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colFailed')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colFallbacks')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colMissingRef')}</TableCell>
                  <TableCell align="right">{t('observability.metrics.colFailureRate')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.by_supplier.map((row) => (
                  <TableRow key={row.client_supplier_id ?? '__none__'}>
                    <TableCell>{row.client_supplier_id ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell>{row.client_id ?? t('observability.metrics.unknownId')}</TableCell>
                    <TableCell align="right">{row.runs_total}</TableCell>
                    <TableCell align="right">{row.runs_failed}</TableCell>
                    <TableCell align="right">{row.fallback_runs}</TableCell>
                    <TableCell align="right">{row.missing_reference_runs}</TableCell>
                    <TableCell align="right">{pctLabel(row.failure_rate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              {t('observability.metrics.tableProviderModel')}
            </Typography>
            <Table size="small">
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
                {data.by_provider_model.map((row, idx) => (
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
        </Stack>
      ) : null}
    </Box>
  );
}
