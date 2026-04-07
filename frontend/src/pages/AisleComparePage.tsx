/**
 * Phase 6 — explicit two-run benchmark compare (read-only). Query: jobAId, jobBId.
 */

import { useMemo } from 'react';
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
import { getApiErrorMessage } from '../utils/apiErrors';
import { useAppSnackbar } from '../components/ui';

export default function AisleComparePage() {
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

  const titleSuffix = useMemo(() => {
    if (!jobAId || !jobBId) return '';
    return `${jobAId.slice(0, 8)}… vs ${jobBId.slice(0, 8)}…`;
  }, [jobAId, jobBId]);

  if (!inventoryId || !aisleId) {
    return <Alert severity="warning">Missing inventory or aisle.</Alert>;
  }

  const breadcrumbs = [
    { label: 'Inventories', to: '/inventories' as const },
    ...(inventory ? [{ label: inventory.name, to: `/inventories/${inventoryId}` as const }] : []),
    {
      label: aisle?.code ?? 'Aisle',
      to: `/inventories/${inventoryId}/aisles/${aisleId}/positions` as const,
    },
    { label: 'Compare runs' },
  ];

  const errMsg =
    compareQuery.isError && compareQuery.error
      ? getApiErrorMessage(
          compareQuery.error instanceof ApiError ? compareQuery.error : new ApiError(String(compareQuery.error)),
          'Failed to load compare'
        )
      : null;

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={`Compare runs ${titleSuffix}`}
        subtitle={inventory?.name ?? '—'}
        actions={
          <Button
            size="small"
            variant="outlined"
            onClick={() => navigate(`/inventories/${inventoryId}/aisles/${aisleId}/positions`)}
          >
            Back to results
          </Button>
        }
      />

      <Alert severity="info" sx={{ mb: 2 }}>
        Read-only benchmark compare (separate from default operational analytics). Row pairing uses a best-effort
        key (SKU, then position code, else per-run id) — not guaranteed entity identity. Promoting a run only
        updates the operational pointer; corrections are not copied automatically between runs.
      </Alert>

      {(!jobAId || !jobBId) && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Add <code>?jobAId=…&amp;jobBId=…</code> (two <strong>different</strong> runs for this aisle). Open Compare
          from aisle results, or use the analytics benchmark compare API for the same payload.
          {jobsQuery.data?.jobs?.length ? (
            <Typography variant="body2" sx={{ mt: 1 }}>
              Recent runs: {jobsQuery.data.jobs.map((j) => j.id.slice(0, 8)).join(', ')}…
            </Typography>
          ) : null}
        </Alert>
      )}

      {compareQuery.isFetching ? <Typography sx={{ mb: 2 }}>Loading compare…</Typography> : null}
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
                  showSnackbar(getApiErrorMessage(err, 'Export failed'), 'error');
                }
              }}
            >
              Export compare table (CSV)
            </Button>
          </Box>

          {(compareQuery.data.raw_fetch_truncated.job_a || compareQuery.data.raw_fetch_truncated.job_b) && (
            <Alert severity="warning">
              Raw row load reached the server cap for one or both runs — compare totals <strong>may</strong> be
              incomplete. The flag means the cap was hit, not that extra rows were proven to exist.
            </Alert>
          )}

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            {(['run_a', 'run_b'] as const).map((side) => {
              const r = compareQuery.data![side];
              return (
                <Paper key={side} sx={{ p: 2, flex: '1 1 320px' }} variant="outlined">
                  <Typography variant="subtitle2" color="text.secondary">
                    {side === 'run_a' ? 'Run A' : 'Run B'}
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {r.job_id}
                  </Typography>
                  <Typography variant="caption" display="block" color="text.secondary">
                    {r.status} · {r.provider_name ?? '—'} · {r.model_name ?? '—'} · {r.prompt_key ?? '—'} ·{' '}
                    {r.prompt_version ?? '—'}
                  </Typography>
                  <Typography variant="caption" display="block" color="text.secondary">
                    Created {r.created_at}
                  </Typography>
                  <Table size="small" sx={{ mt: 1 }}>
                    <TableBody>
                      <TableRow>
                        <TableCell>Consolidated positions</TableCell>
                        <TableCell align="right">{r.metrics.consolidated_positions}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Total quantity</TableCell>
                        <TableCell align="right">{r.metrics.total_quantity}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Unknown internal code</TableCell>
                        <TableCell align="right">{r.metrics.unknown_internal_code_count}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Needs review</TableCell>
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
              Diff summary
            </Typography>
            <Typography variant="body2">
              Only in A: {compareQuery.data.diff_summary.keys_only_in_a} · Only in B:{' '}
              {compareQuery.data.diff_summary.keys_only_in_b} · In both: {compareQuery.data.diff_summary.keys_in_both}
              · Qty changed: {compareQuery.data.diff_summary.quantity_changed} · SKU changed:{' '}
              {compareQuery.data.diff_summary.sku_changed} · Position code changed:{' '}
              {compareQuery.data.diff_summary.position_code_changed}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              “Only in A/B” can include rows that moved keys between runs (heuristic matching).
            </Typography>
          </Paper>

          <Paper sx={{ p: 2 }} variant="outlined">
            <Typography variant="subtitle1" gutterBottom>
              Diff rows {compareQuery.data.diff_rows_truncated ? '(truncated)' : ''}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Key</TableCell>
                  <TableCell>Side</TableCell>
                  <TableCell align="right">Qty A</TableCell>
                  <TableCell align="right">Qty B</TableCell>
                  <TableCell>SKU A</TableCell>
                  <TableCell>SKU B</TableCell>
                  <TableCell>Pos A</TableCell>
                  <TableCell>Pos B</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {compareQuery.data.diff_rows.map((row) => (
                  <TableRow key={`${row.match_key}-${row.side}`}>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{row.match_key}</TableCell>
                    <TableCell>{row.side}</TableCell>
                    <TableCell align="right">{row.quantity_a ?? '—'}</TableCell>
                    <TableCell align="right">{row.quantity_b ?? '—'}</TableCell>
                    <TableCell>{row.sku_a ?? '—'}</TableCell>
                    <TableCell>{row.sku_b ?? '—'}</TableCell>
                    <TableCell>{row.position_code_a ?? '—'}</TableCell>
                    <TableCell>{row.position_code_b ?? '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {compareQuery.data.diff_rows.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No differences in the compared consolidation keys.
              </Typography>
            ) : null}
          </Paper>
        </Box>
      ) : null}
    </>
  );
}
