/**
 * Phase 6 — explicit two-run benchmark compare (read-only). Query: jobAId, jobBId.
 */

import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { PageHeader } from '../components/shell';
import { useInventoryDetail, useAisleBenchmarkCompare, useAisleJobsList, useAislesList } from '../hooks';
import { downloadAisleBenchmarkExportCsv } from '../api/client';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { useAppSnackbar } from '../components/ui';

export default function AisleComparePage() {
  const { t } = useTranslation();
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();

  const jobAId = searchParams.get('jobAId')?.trim() || '';
  const jobBId = searchParams.get('jobBId')?.trim() || '';

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId);
  const compareQuery = useAisleBenchmarkCompare(inventoryId, aisleId, jobAId, jobBId);
  const jobsQuery = useAisleJobsList(inventoryId, aisleId, { limit: 200 });

  const inventory = inventoryQuery.data;
  const aisle = aislesQuery.data?.items?.find((a) => a.id === aisleId);

  useEffect(() => {
    if (!inventoryId || !aisleId) return;
    if (!inventoryQuery.isSuccess) return;
    if (!inventory) return;
    if (inventory.processing_mode !== 'test') {
      navigate(`/inventories/${inventoryId}/aisles/${aisleId}/positions`, { replace: true });
    }
  }, [aisleId, inventory, inventoryId, inventoryQuery.isSuccess, navigate]);

  const titleSuffix = useMemo(() => {
    if (!jobAId || !jobBId) return '';
    return `${jobAId.slice(0, 8)}… vs ${jobBId.slice(0, 8)}…`;
  }, [jobAId, jobBId]);

  if (!inventoryId || !aisleId) {
    return <Alert severity="warning">{t('compare.missing_params')}</Alert>;
  }

  const breadcrumbs = [
    { label: t('aisle.breadcrumb_inventories'), to: '/' as const },
    ...(inventory ? [{ label: inventory.name, to: `/inventories/${inventoryId}` as const }] : []),
    {
      label: aisle?.code ?? t('common.aisle'),
      to: `/inventories/${inventoryId}/aisles/${aisleId}/positions` as const,
    },
    { label: t('compare.breadcrumb') },
  ];

  const errMsg =
    compareQuery.isError && compareQuery.error
      ? resolveApiErrorMessage(
          compareQuery.error instanceof ApiError ? compareQuery.error : new ApiError(String(compareQuery.error)),
          'errors.load_compare',
        )
      : null;

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={t('compare.title_with_ids', {
          suffix: titleSuffix.trim() ? ` ${titleSuffix.trim()}` : '',
        })}
        subtitle={inventory?.name ?? t('common.em_dash')}
        actions={
          <Button
            size="small"
            variant="outlined"
            onClick={() => navigate(`/inventories/${inventoryId}/aisles/${aisleId}/positions`)}
          >
            {t('compare.back_to_results')}
          </Button>
        }
      />

      <Alert severity="info" sx={{ mb: 2 }}>
        {t('compare.info_benchmark')}
      </Alert>

      {(!jobAId || !jobBId) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('compare.warning_need_jobs')}
          {jobsQuery.data?.jobs?.length ? (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {t('compare.recent_runs', {
                ids: jobsQuery.data.jobs.map((j) => j.id.slice(0, 8)).join(', '),
              })}
            </Typography>
          ) : null}
        </Alert>
      )}

      {compareQuery.isFetching ? <Typography sx={{ mb: 2 }}>{t('compare.loading')}</Typography> : null}
      {errMsg ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errMsg}
        </Alert>
      ) : null}

      {compareQuery.data ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
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
