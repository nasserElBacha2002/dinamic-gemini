/**
 * Analytics — benchmark compare (read-only two-run diff). Query: aisleId, jobAId, jobBId.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  Tooltip,
} from '@mui/material';
import { PageHeader } from '../../components/shell';
import CompareRunJobPickers from '../../components/compare/CompareRunJobPickers';
import { useInventoryDetail, useAisleBenchmarkCompare, useAisleJobsList, useAislesList } from '../../hooks';
import { downloadAisleBenchmarkExportCsv } from '../../api/client';
import { ApiError } from '../../api/types';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { useAppSnackbar } from '../../components/ui';
import { pathToAislePositions } from '../../utils/resultRoutes';

function formatCostDisplay(
  run: {
    llm_cost_snapshot?: {
      billing_currency?: string | null;
      computed_cost?: { total_cost?: string | null; currency?: string | null };
      capture_status?: string;
      capture_notes?: string[];
    } | null;
  },
  unavailableLabel: string
): {
  value: string;
  details: string | null;
} {
  const snap = run.llm_cost_snapshot;
  if (!snap) return { value: unavailableLabel, details: null };
  const total = snap.computed_cost?.total_cost?.trim();
  const currency = snap.computed_cost?.currency?.trim() || snap.billing_currency?.trim();
  const status = snap.capture_status ?? 'unavailable';
  const notes = Array.isArray(snap.capture_notes) ? snap.capture_notes : [];
  const details = [`status=${status}`, ...notes].join(' | ');
  if (!total) {
    return { value: unavailableLabel, details };
  }
  return { value: `${total} ${currency || ''}`.trim(), details };
}

export default function CompareRunsPage() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();

  const aisleId = searchParams.get('aisleId')?.trim() || '';
  const jobAId = searchParams.get('jobAId')?.trim() || '';
  const jobBId = searchParams.get('jobBId')?.trim() || '';

  const [draftJobA, setDraftJobA] = useState('');
  const [draftJobB, setDraftJobB] = useState('');

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });

  const compareQueryEnabled = Boolean(
    (inventoryId ?? '').trim() &&
      aisleId &&
      jobAId &&
      jobBId &&
      jobAId !== jobBId
  );
  const compareQuery = useAisleBenchmarkCompare(
    inventoryId,
    aisleId || undefined,
    jobAId,
    jobBId,
    { enabled: compareQueryEnabled }
  );
  const jobsQuery = useAisleJobsList(inventoryId, aisleId || undefined, {
    enabled: Boolean(inventoryId && aisleId && inventoryQuery.data),
    limit: 200,
  });

  const inventory = inventoryQuery.data;
  const aislesItems = aislesQuery.data?.items ?? [];
  const aisle = aislesItems.find((a) => a.id === aisleId);
  const jobs = jobsQuery.data?.jobs ?? [];
  /** Avoid MUI out-of-range Select when URL aisle is ahead of the aisles list query. */
  const aisleSelectValue =
    aisleId && aislesQuery.isFetched && aislesItems.some((a) => a.id === aisleId) ? aisleId : '';

  useEffect(() => {
    if (!inventoryId) return;
    if (!inventoryQuery.isSuccess) return;
    if (!inventory) return;
    if (inventory.processing_mode !== 'test') {
      navigate(`/inventories/${inventoryId}`, { replace: true });
    }
  }, [inventory, inventoryId, inventoryQuery.isSuccess, navigate]);

  useEffect(() => {
    setDraftJobA(jobAId);
    setDraftJobB(jobBId);
  }, [jobAId, jobBId]);

  useEffect(() => {
    if (jobAId || jobBId || jobs.length < 2) return;
    const a = jobs[0]?.id ?? '';
    const b = jobs.find((j) => j.id !== a)?.id ?? '';
    if (a && b && a !== b) {
      setDraftJobA(a);
      setDraftJobB(b);
    }
  }, [jobAId, jobBId, jobs]);

  const applyAisleToUrl = useCallback(
    (nextAisleId: string) => {
      setSearchParams((prev) => {
        const p = new URLSearchParams(prev);
        if (nextAisleId) {
          p.set('aisleId', nextAisleId);
        } else {
          p.delete('aisleId');
        }
        p.delete('jobAId');
        p.delete('jobBId');
        return p;
      });
    },
    [setSearchParams]
  );

  const applyJobsToUrl = useCallback(() => {
    if (!draftJobA || !draftJobB || draftJobA === draftJobB) return;
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('jobAId', draftJobA);
      p.set('jobBId', draftJobB);
      return p;
    });
  }, [draftJobA, draftJobB, setSearchParams]);

  const titleSuffix = useMemo(() => {
    if (!jobAId || !jobBId) return '';
    return `${jobAId.slice(0, 8)}… vs ${jobBId.slice(0, 8)}…`;
  }, [jobAId, jobBId]);

  if (!inventoryId) {
    return <Alert severity="warning">{t('compare.missing_inventory')}</Alert>;
  }

  const breadcrumbs = [
    { label: t('aisle.breadcrumb_inventories'), to: '/' as const },
    ...(inventory ? [{ label: inventory.name, to: `/inventories/${inventoryId}` as const }] : []),
    { label: t('analytics.compare_runs_breadcrumb') },
  ];

  const errMsg =
    compareQuery.isError && compareQuery.error
      ? resolveApiErrorMessage(
          compareQuery.error instanceof ApiError ? compareQuery.error : new ApiError(String(compareQuery.error)),
          'errors.load_compare'
        )
      : null;

  const backHref =
    aisleId && inventoryId ? pathToAislePositions(inventoryId, aisleId) : `/inventories/${inventoryId}`;

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={t('analytics.compare_runs_page_title')}
        subtitle={t('compare.title_with_ids', {
          suffix: titleSuffix.trim() ? ` ${titleSuffix.trim()}` : '',
        })}
        actions={
          <Button size="small" variant="outlined" onClick={() => navigate(backHref)}>
            {aisleId ? t('compare.back_to_results') : t('analytics.back_to_inventory')}
          </Button>
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="overline" color="text.secondary" display="block">
          {t('analytics.benchmark_context_label')}
        </Typography>
        <Typography variant="body1" sx={{ fontWeight: 600 }}>
          {t('analytics.context_inventory_label')}: {inventory?.name ?? t('common.loading')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {aisleId
            ? t('analytics.context_aisle_label', { code: aisle?.code ?? aisleId.slice(0, 8) })
            : t('analytics.context_aisle_not_selected')}
        </Typography>
        {jobAId && jobBId ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1, fontFamily: 'monospace' }}>
            {t('analytics.context_runs_label')}: {jobAId.slice(0, 12)}… ↔ {jobBId.slice(0, 12)}…
          </Typography>
        ) : null}
      </Paper>

      <Alert severity="info" sx={{ mb: 2 }}>
        {t('compare.info_benchmark')}
      </Alert>

      {!aisleId ? (
        <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-runs-aisle-scope">
          <Typography variant="subtitle2" gutterBottom>
            {t('analytics.select_aisle_title')}
          </Typography>
          <FormControl fullWidth size="small" sx={{ maxWidth: 360 }}>
            <InputLabel id="analytics-aisle-label">{t('common.aisle')}</InputLabel>
            <Select
              labelId="analytics-aisle-label"
              label={t('common.aisle')}
              value=""
              displayEmpty
              onChange={(e) => applyAisleToUrl(String(e.target.value))}
            >
              <MenuItem value="" disabled>
                <em>{t('analytics.select_aisle_placeholder')}</em>
              </MenuItem>
              {aislesItems.map((a) => (
                <MenuItem key={a.id} value={a.id}>
                  {a.code}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Paper>
      ) : (
        <Box
          data-testid="compare-runs-change-aisle"
          sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}
        >
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="switch-aisle-label">{t('analytics.change_aisle')}</InputLabel>
            <Select
              labelId="switch-aisle-label"
              label={t('analytics.change_aisle')}
              value={aisleSelectValue}
              onChange={(e) => applyAisleToUrl(String(e.target.value))}
            >
              {aislesItems.map((a) => (
                <MenuItem key={a.id} value={a.id}>
                  {a.code}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      {aisleId && (!jobAId || !jobBId) ? (
        <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-runs-job-scope">
          <Typography variant="subtitle2" gutterBottom>
            {t('benchmark.compare_two_runs_title')}
          </Typography>
          <CompareRunJobPickers
            jobs={jobs}
            jobA={draftJobA}
            jobB={draftJobB}
            onJobAChange={setDraftJobA}
            onJobBChange={setDraftJobB}
            description={t('benchmark.compare_readonly_explain')}
          />
          <Box sx={{ mt: 2 }}>
            <Button
              variant="contained"
              disabled={!draftJobA || !draftJobB || draftJobA === draftJobB}
              onClick={applyJobsToUrl}
            >
              {t('analytics.load_comparison')}
            </Button>
          </Box>
          {jobs.length ? (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
              {t('compare.recent_runs', {
                ids: jobs.map((j) => j.id.slice(0, 8)).join(', '),
              })}
            </Typography>
          ) : null}
        </Paper>
      ) : null}

      {aisleId && (!jobAId || !jobBId) && !jobs.length && jobsQuery.isFetched ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('compare.warning_need_jobs')}
        </Alert>
      ) : null}

      {compareQuery.isFetching ? <Typography sx={{ mb: 2 }}>{t('compare.loading')}</Typography> : null}
      {errMsg ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errMsg}
        </Alert>
      ) : null}

      {compareQuery.data ? (
        <Box data-testid="compare-runs-results" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={async () => {
                try {
                  await downloadAisleBenchmarkExportCsv(inventoryId, aisleId, { jobAId, jobBId });
                } catch (e) {
                  const err = e instanceof ApiError ? e : new ApiError(String(e));
                  showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
                }
              }}
            >
              {t('compare.export_csv')}
            </Button>
          </Box>

          {(compareQuery.data.raw_fetch_truncated.job_a || compareQuery.data.raw_fetch_truncated.job_b) && (
            <Alert severity="warning">{t('compare.truncation_warning')}</Alert>
          )}

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            {(['run_a', 'run_b'] as const).map((side) => {
              const r = compareQuery.data![side];
              const cost = formatCostDisplay(r, 'Unavailable');
              return (
                <Paper key={side} sx={{ p: 2, flex: '1 1 320px' }} variant="outlined">
                  <Typography variant="subtitle2" color="text.secondary">
                    {side === 'run_a' ? t('results.run_a_label') : t('results.run_b_label')}
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {r.job_id}
                  </Typography>
                  <Typography variant="caption" display="block" color="text.secondary">
                    {r.status} · {r.provider_name ?? t('common.em_dash')} · {r.model_name ?? t('common.em_dash')} ·{' '}
                    {r.prompt_key ?? t('common.em_dash')} · {r.prompt_version ?? t('common.em_dash')}
                  </Typography>
                  <Typography variant="caption" display="block" color="text.secondary">
                    {t('compare.created_at', { date: r.created_at })}
                  </Typography>
                  <Table size="small" sx={{ mt: 1 }}>
                    <TableBody>
                      <TableRow>
                        <TableCell>{t('compare.metric_consolidated')}</TableCell>
                        <TableCell align="right">{r.metrics.consolidated_positions}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>{t('compare.metric_total_qty')}</TableCell>
                        <TableCell align="right">{r.metrics.total_quantity}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>{t('compare.metric_unknown_code')}</TableCell>
                        <TableCell align="right">{r.metrics.unknown_internal_code_count}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>{t('compare.metric_needs_review')}</TableCell>
                        <TableCell align="right">{r.metrics.needs_review_count}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>{t('compare.metric_total_cost', 'Total cost')}</TableCell>
                        <TableCell align="right">
                          {cost.details ? (
                            <Tooltip title={cost.details}>
                              <span>{cost.value}</span>
                            </Tooltip>
                          ) : (
                            cost.value
                          )}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </Paper>
              );
            })}
          </Box>

          <Paper sx={{ p: 2 }} variant="outlined">
            <Typography variant="subtitle1" gutterBottom>
              {t('compare.diff_summary_title')}
            </Typography>
            <Typography variant="body2">
              {t('compare.diff_summary_stats', {
                onlyA: compareQuery.data.diff_summary.keys_only_in_a,
                onlyB: compareQuery.data.diff_summary.keys_only_in_b,
                both: compareQuery.data.diff_summary.keys_in_both,
                qty: compareQuery.data.diff_summary.quantity_changed,
                sku: compareQuery.data.diff_summary.sku_changed,
                pos: compareQuery.data.diff_summary.position_code_changed,
              })}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              {t('compare.diff_summary_note')}
            </Typography>
          </Paper>

          <Paper sx={{ p: 2 }} variant="outlined">
            <Typography variant="subtitle1" gutterBottom>
              {t('compare.diff_rows_title')}{' '}
              {compareQuery.data.diff_rows_truncated ? t('compare.diff_rows_truncated') : ''}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('compare.col_key')}</TableCell>
                  <TableCell>{t('compare.col_side')}</TableCell>
                  <TableCell align="right">{t('compare.col_qty_a')}</TableCell>
                  <TableCell align="right">{t('compare.col_qty_b')}</TableCell>
                  <TableCell>{t('compare.col_sku_a')}</TableCell>
                  <TableCell>{t('compare.col_sku_b')}</TableCell>
                  <TableCell>{t('compare.col_pos_a')}</TableCell>
                  <TableCell>{t('compare.col_pos_b')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {compareQuery.data.diff_rows.map((row) => (
                  <TableRow key={`${row.match_key}-${row.side}`}>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{row.match_key}</TableCell>
                    <TableCell>{row.side}</TableCell>
                    <TableCell align="right">{row.quantity_a ?? t('common.em_dash')}</TableCell>
                    <TableCell align="right">{row.quantity_b ?? t('common.em_dash')}</TableCell>
                    <TableCell>{row.sku_a ?? t('common.em_dash')}</TableCell>
                    <TableCell>{row.sku_b ?? t('common.em_dash')}</TableCell>
                    <TableCell>{row.position_code_a ?? t('common.em_dash')}</TableCell>
                    <TableCell>{row.position_code_b ?? t('common.em_dash')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {compareQuery.data.diff_rows.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('compare.no_diff_rows')}
              </Typography>
            ) : null}
          </Paper>
        </Box>
      ) : null}
    </>
  );
}
