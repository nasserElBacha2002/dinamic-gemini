import { useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { PageHeader } from '../../components/shell';
import { useAisleBenchmarkCompareMany, useAisleJobsList, useAislesList, useInventoryDetail } from '../../hooks';
import type { BenchmarkCompareManyDiff, JobSummary } from '../../api/types';
import { ApiError } from '../../api/types';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { ROUTE_HOME, pathToInventory, pathToInventoryAnalyticsCompare } from '../../constants/appRoutes';
import {
  formatExecutionDurationHuman,
  formatSignedDurationHuman,
  wallClockSecondsFromJobTimestamps,
} from '../../utils/benchmarkExecutionTime';

const MIN_COMPARE_JOBS = 2;
const MAX_COMPARE_JOBS = 3;

type AppliedState = {
  aisleId: string;
  jobIds: string[];
  baseline: string;
};

function parseJobIds(raw: string | null): string[] {
  if (!raw) return [];
  const out: string[] = [];
  for (const token of raw.split(',')) {
    const trimmed = token.trim();
    if (!trimmed) continue;
    out.push(trimmed);
  }
  return out;
}

function parseAppliedState(searchParams: URLSearchParams): AppliedState {
  return {
    aisleId: searchParams.get('aisleId')?.trim() ?? '',
    jobIds: parseJobIds(searchParams.get('jobIds')),
    baseline: searchParams.get('baseline')?.trim() ?? '',
  };
}

function isAppliedStateValid(state: AppliedState): boolean {
  const hasDuplicates = new Set(state.jobIds).size !== state.jobIds.length;
  return Boolean(
    state.aisleId &&
      state.jobIds.length >= MIN_COMPARE_JOBS &&
      state.jobIds.length <= MAX_COMPARE_JOBS &&
      !hasDuplicates &&
      state.baseline &&
      state.jobIds.includes(state.baseline)
  );
}

/** Selection order is meaningful for compare-many; reordering counts as a real change. */
function sameSelection(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, idx) => id === b[idx]);
}

function signedValue(value: number): string {
  if (value > 0) return `+${value}`;
  return String(value);
}

function semanticColor(value: number, higherIsWorse: boolean): 'success.main' | 'error.main' | 'text.primary' {
  if (value === 0) return 'text.primary';
  if (higherIsWorse) return value > 0 ? 'error.main' : 'success.main';
  return value > 0 ? 'success.main' : 'error.main';
}

function buildDraftError(aisleId: string, jobIds: string[], baseline: string, t: (key: string) => string): string | null {
  if (new Set(jobIds).size !== jobIds.length) return t('compare_many.errors.duplicate_jobs');
  if (!aisleId) return t('compare_many.errors.select_aisle');
  if (jobIds.length < MIN_COMPARE_JOBS) return t('compare_many.errors.pick_two_jobs');
  if (jobIds.length > MAX_COMPARE_JOBS) return t('compare_many.errors.pick_max_three_jobs');
  if (!baseline || !jobIds.includes(baseline)) return t('compare_many.errors.pick_valid_baseline');
  return null;
}

function orderJobsForDisplay(jobIds: string[], baseline: string): string[] {
  const rest = jobIds.filter((id) => id !== baseline);
  return baseline ? [baseline, ...rest] : jobIds;
}

function hasNoDifferences(comp: BenchmarkCompareManyDiff): boolean {
  const s = comp.diff_summary;
  return (
    s.keys_only_in_a === 0 &&
    s.keys_only_in_b === 0 &&
    s.quantity_changed === 0 &&
    s.sku_changed === 0 &&
    s.position_code_changed === 0
  );
}

function displayJobName(job: JobSummary): string {
  return `${job.id.slice(0, 8)}…`;
}

function compareRunExecutionLabel(
  run: { execution_time_human?: string | null; execution_time_seconds?: number | null },
  t: TFunction
): string {
  if (run.execution_time_human) {
    return run.execution_time_human;
  }
  if (run.execution_time_seconds != null) {
    return formatExecutionDurationHuman(run.execution_time_seconds);
  }
  return t('compare.execution_unavailable');
}

function compareManyExecutionInsight(t: TFunction, comp: BenchmarkCompareManyDiff): string | null {
  const dExec = comp.delta.execution_time_delta;
  const dUnk = comp.delta.unknown_internal_code_diff;
  if (dExec == null) {
    return null;
  }
  if (dExec > 0 && dUnk < 0) {
    return t('compare_many.insight_slower_but_unknown_down', {
      time: formatSignedDurationHuman(dExec),
      unknown: String(Math.abs(dUnk)),
    });
  }
  if (dExec < 0 && dUnk > 0) {
    return t('compare_many.insight_faster_but_unknown_up', {
      time: formatSignedDurationHuman(dExec),
      unknown: String(dUnk),
    });
  }
  return null;
}

export const __testables = {
  buildDraftError,
};

export default function CompareManyRunsPage() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const applied = useMemo(() => parseAppliedState(searchParams), [searchParams]);
  const correctionNoticeRef = useRef<string | null>(null);
  const [showBaselineAdjustedNotice, setShowBaselineAdjustedNotice] = useState(false);
  const [expandedTargetJobId, setExpandedTargetJobId] = useState<string | null>(null);

  const [draftAisleId, setDraftAisleId] = useState(applied.aisleId);
  const [draftJobIds, setDraftJobIds] = useState<string[]>(applied.jobIds);
  const [draftBaseline, setDraftBaseline] = useState(applied.baseline);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });
  const jobsQuery = useAisleJobsList(inventoryId, draftAisleId || undefined, {
    enabled: Boolean(inventoryId && draftAisleId && inventoryQuery.data),
    limit: 200,
  });

  const appliedValid = isAppliedStateValid(applied);
  const compareQuery = useAisleBenchmarkCompareMany(
    inventoryId,
    applied.aisleId || undefined,
    applied.jobIds,
    applied.baseline,
    { enabled: appliedValid, includeDiffRows: false }
  );
  const enrichedCompareManyQuery = useAisleBenchmarkCompareMany(
    inventoryId,
    applied.aisleId || undefined,
    applied.jobIds,
    applied.baseline,
    { enabled: appliedValid && Boolean(expandedTargetJobId), includeDiffRows: true }
  );

  // Expanding one block enriches the full compare-many payload (all comparisons), then each block renders its own slice.
  const effectiveData = enrichedCompareManyQuery.data ?? compareQuery.data;
  const aisles = aislesQuery.data?.items ?? [];
  const jobs = jobsQuery.data?.jobs ?? [];
  const sortedJobsForPicker = useMemo(() => {
    const list = [...jobs];
    list.sort((a, b) => {
      const da = wallClockSecondsFromJobTimestamps(a.started_at, a.finished_at);
      const db = wallClockSecondsFromJobTimestamps(b.started_at, b.finished_at);
      const ra = da ?? Number.POSITIVE_INFINITY;
      const rb = db ?? Number.POSITIVE_INFINITY;
      if (ra !== rb) return ra - rb;
      return b.created_at.localeCompare(a.created_at);
    });
    return list;
  }, [jobs]);
  const aisleSelectValue = draftAisleId && aisles.some((aisle) => aisle.id === draftAisleId) ? draftAisleId : '';
  const baselineSelectValue = draftBaseline && draftJobIds.includes(draftBaseline) ? draftBaseline : '';
  const draftError = buildDraftError(draftAisleId, draftJobIds, draftBaseline, t);
  const dirty =
    draftAisleId !== applied.aisleId || draftBaseline !== applied.baseline || !sameSelection(draftJobIds, applied.jobIds);

  useEffect(() => {
    if (!inventoryId || !inventoryQuery.isSuccess || !inventoryQuery.data) return;
    if (inventoryQuery.data.processing_mode !== 'test') {
      navigate(pathToInventory(inventoryId), { replace: true });
    }
  }, [inventoryId, inventoryQuery.data, inventoryQuery.isSuccess, navigate]);

  useEffect(() => {
    setDraftAisleId(applied.aisleId);
    setDraftJobIds(applied.jobIds);
    setDraftBaseline(applied.baseline);
    setExpandedTargetJobId(null);
  }, [applied.aisleId, applied.baseline, applied.jobIds]);

  useEffect(() => {
    // URL correction policy: only baseline is auto-corrected, and only when the rest of applied state is already valid.
    // Other invalid URL states (duplicate jobs, bad count, missing aisle) are shown as invalid without URL mutation.
    if (!applied.aisleId) return;
    if (applied.jobIds.length < MIN_COMPARE_JOBS || applied.jobIds.length > MAX_COMPARE_JOBS) return;
    if (new Set(applied.jobIds).size !== applied.jobIds.length) return;
    if (!applied.jobIds.length) return;
    if (applied.baseline && applied.jobIds.includes(applied.baseline)) return;
    const nextBaseline = applied.jobIds[0];
    if (!nextBaseline) return;
    const correctionKey = `${applied.aisleId}|${applied.jobIds.join(',')}|${nextBaseline}`;
    if (correctionNoticeRef.current === correctionKey) return;
    correctionNoticeRef.current = correctionKey;
    setShowBaselineAdjustedNotice(true);
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('baseline', nextBaseline);
      return p;
    }, { replace: true });
  }, [applied.aisleId, applied.baseline, applied.jobIds, setSearchParams]);

  const applyDraftToUrl = () => {
    if (draftError) return;
    const safeBaseline = draftJobIds.includes(draftBaseline) ? draftBaseline : draftJobIds[0] ?? '';
    if (!safeBaseline) return;
    if (safeBaseline !== draftBaseline) {
      setShowBaselineAdjustedNotice(true);
    }
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('aisleId', draftAisleId);
      p.set('jobIds', draftJobIds.join(','));
      p.set('baseline', safeBaseline);
      return p;
    });
  };

  const orderedJobIds = orderJobsForDisplay(applied.jobIds, applied.baseline);
  const jobsById = new Map((effectiveData?.jobs ?? []).map((job) => [job.job_id, job]));
  const orderedComparisons = (effectiveData?.comparisons ?? []).slice().sort((a, b) => {
    return orderedJobIds.indexOf(a.target_job_id) - orderedJobIds.indexOf(b.target_job_id);
  });

  const compareErrorMessage =
    (compareQuery.isError || enrichedCompareManyQuery.isError) && (compareQuery.error || enrichedCompareManyQuery.error)
      ? resolveApiErrorMessage(
          (compareQuery.error || enrichedCompareManyQuery.error) instanceof ApiError
            ? (compareQuery.error || enrichedCompareManyQuery.error)
            : new ApiError(String(compareQuery.error || enrichedCompareManyQuery.error)),
          'errors.load_compare'
        )
      : null;

  if (!inventoryId) {
    return <Alert severity="warning">{t('compare_many.missing_inventory')}</Alert>;
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
          ...(inventoryQuery.data ? [{ label: inventoryQuery.data.name, to: pathToInventory(inventoryId) }] : []),
          { label: t('analytics.compare_many_runs_breadcrumb') },
        ]}
        title={t('analytics.compare_many_runs_page_title')}
        subtitle={t('compare_many.subtitle')}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" variant="outlined" onClick={() => navigate(pathToInventoryAnalyticsCompare(inventoryId))}>
              {t('compare_many.open_ab_compare')}
            </Button>
          </Box>
        }
      />

      {showBaselineAdjustedNotice ? (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          onClose={() => {
            setShowBaselineAdjustedNotice(false);
          }}
        >
          {t('compare_many.baseline_adjusted_notice')}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-many-controls">
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
          <FormControl size="small">
            <InputLabel id="compare-many-aisle-label">{t('common.aisle')}</InputLabel>
            <Select
              labelId="compare-many-aisle-label"
              value={aisleSelectValue}
              label={t('common.aisle')}
              onChange={(e) => {
                setDraftAisleId(String(e.target.value));
                setDraftJobIds([]);
                setDraftBaseline('');
              }}
            >
              {aisles.map((aisle) => (
                <MenuItem key={aisle.id} value={aisle.id}>
                  {aisle.code}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small">
            <InputLabel id="compare-many-jobids-label">{t('compare_many.job_ids_label')}</InputLabel>
            <Select
              labelId="compare-many-jobids-label"
              multiple
              value={draftJobIds}
              label={t('compare_many.job_ids_label')}
              onChange={(e) => {
                const next = (e.target.value as string[]).slice(0, MAX_COMPARE_JOBS);
                setDraftJobIds(next);
                if (!next.includes(draftBaseline)) {
                  setDraftBaseline(next[0] ?? '');
                }
              }}
              renderValue={(selected) =>
                (selected as string[])
                  .map((id) => sortedJobsForPicker.find((job) => job.id === id) ?? jobs.find((job) => job.id === id))
                  .filter((job): job is JobSummary => Boolean(job))
                  .map(displayJobName)
                  .join(', ')
              }
            >
              {sortedJobsForPicker.map((job) => (
                <MenuItem key={job.id} value={job.id} disabled={!draftJobIds.includes(job.id) && draftJobIds.length >= MAX_COMPARE_JOBS}>
                  {displayJobName(job)} · {job.status}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small">
            <InputLabel id="compare-many-baseline-label">{t('compare_many.baseline_label')}</InputLabel>
            <Select
              labelId="compare-many-baseline-label"
              value={baselineSelectValue}
              label={t('compare_many.baseline_label')}
              onChange={(e) => setDraftBaseline(String(e.target.value))}
            >
              {draftJobIds.map((id) => (
                <MenuItem key={id} value={id}>
                  {id.slice(0, 8)}…
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Button variant="contained" onClick={applyDraftToUrl} disabled={Boolean(draftError) || !dirty}>
              {t('compare_many.apply')}
            </Button>
            {dirty ? <Chip size="small" label={t('compare_many.changes_not_applied')} variant="outlined" /> : null}
          </Box>
        </Box>
        {draftError ? (
          <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
            {draftError}
          </Typography>
        ) : null}
      </Paper>

      {!appliedValid ? (
        <Alert severity="info" data-testid="compare-many-empty-state">
          {t('compare_many.empty_instruction')}
        </Alert>
      ) : null}

      {compareErrorMessage ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {compareErrorMessage}
        </Alert>
      ) : null}

      {appliedValid && (compareQuery.isFetching || (!compareQuery.data && compareQuery.isLoading)) ? (
        <Box sx={{ display: 'grid', gap: 2 }} data-testid="compare-many-loading">
          <Skeleton variant="rounded" height={80} />
          <Skeleton variant="rounded" height={120} />
          <Skeleton variant="rounded" height={160} />
        </Box>
      ) : null}

      {effectiveData ? (
        <Box data-testid="compare-many-results" sx={{ display: 'grid', gap: 2 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle1">{t('compare_many.summary_title')}</Typography>
              <Tooltip title={t('compare_many.summary_not_ranking')}>
                <InfoOutlinedIcon fontSize="small" color="action" />
              </Tooltip>
            </Box>
            <Typography variant="body2">{t('compare_many.summary_not_ranking')}</Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              {t('compare_many.summary_values', {
                jobs: effectiveData.summary.job_count,
                qtyMin: effectiveData.summary.min_total_quantity,
                qtyMax: effectiveData.summary.max_total_quantity,
                reviewMin: effectiveData.summary.min_needs_review,
                reviewMax: effectiveData.summary.max_needs_review,
                consolidatedMin: effectiveData.summary.min_consolidated_positions,
                consolidatedMax: effectiveData.summary.max_consolidated_positions,
                unknownMin: effectiveData.summary.min_unknown_internal_code_count,
                unknownMax: effectiveData.summary.max_unknown_internal_code_count,
              })}
            </Typography>
            {effectiveData.summary.min_execution_time_seconds != null &&
            effectiveData.summary.max_execution_time_seconds != null ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                {t('compare_many.summary_exec_range', {
                  min: formatExecutionDurationHuman(effectiveData.summary.min_execution_time_seconds),
                  max: formatExecutionDurationHuman(effectiveData.summary.max_execution_time_seconds),
                })}
              </Typography>
            ) : (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                {t('compare_many.summary_exec_unavailable')}
              </Typography>
            )}
          </Paper>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' } }}>
            {orderedJobIds.map((jobId) => {
              const job = jobsById.get(jobId);
              if (!job) return null;
              const isBaseline = jobId === effectiveData.baseline_job_id;
              return (
                <Paper
                  key={jobId}
                  variant="outlined"
                  sx={{ p: 2, borderColor: isBaseline ? 'primary.main' : 'divider' }}
                  data-testid={isBaseline ? 'compare-many-baseline-card' : undefined}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontFamily: 'monospace' }}>
                      {job.job_id}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.75 }}>
                      {isBaseline ? <Chip size="small" color="primary" label={t('compare_many.baseline_chip')} /> : null}
                      <Chip
                        size="small"
                        color={job.status === 'succeeded' ? 'default' : 'warning'}
                        label={t('compare_many.status_chip', { status: job.status })}
                      />
                    </Box>
                  </Box>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {job.provider_name ?? t('common.em_dash')} · {job.model_name ?? t('common.em_dash')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    {t('compare_many.job_execution_time', { value: compareRunExecutionLabel(job, t) })}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    {t('compare_many.job_metrics', {
                      qty: job.metrics.total_quantity,
                      review: job.metrics.needs_review_count,
                      unknown: job.metrics.unknown_internal_code_count,
                      consolidated: job.metrics.consolidated_positions,
                    })}
                  </Typography>
                </Paper>
              );
            })}
          </Box>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle2">{t('compare_many.delta_legend_title')}</Typography>
              <Tooltip title={t('compare_many.delta_legend_body')}>
                <InfoOutlinedIcon fontSize="small" color="action" />
              </Tooltip>
            </Box>
            <Typography variant="caption" color="text.secondary">
              {t('compare_many.delta_legend_body')}
            </Typography>
          </Paper>

          {orderedComparisons.map((comp) => {
            const expanded = expandedTargetJobId === comp.target_job_id;
            const diffRowsLoading = expanded && enrichedCompareManyQuery.isFetching && !enrichedCompareManyQuery.data;
            const noDifferences = hasNoDifferences(comp);
            const insightLine = compareManyExecutionInsight(t, comp);
            return (
              <Paper variant="outlined" sx={{ p: 2 }} key={comp.target_job_id} data-testid="compare-many-comparison-block">
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="subtitle1">
                    {t('compare_many.baseline_vs_target', {
                      baseline: comp.baseline_job_id.slice(0, 8),
                      target: comp.target_job_id.slice(0, 8),
                    })}
                  </Typography>
                  <Button
                    size="small"
                    onClick={() => setExpandedTargetJobId(expanded ? null : comp.target_job_id)}
                    endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  >
                    {expanded ? t('common.hide') : t('compare_many.show_diff_rows')}
                  </Button>
                </Box>
                {jobsById.get(comp.target_job_id)?.status !== 'succeeded' ? (
                  <Alert severity="warning" sx={{ mb: 1 }}>
                    {t('compare_many.target_non_ideal_status')}
                  </Alert>
                ) : null}

                <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
                  <Typography sx={{ color: semanticColor(comp.delta.needs_review_diff, true) }}>
                    {t('compare_many.delta_needs_review', { value: signedValue(comp.delta.needs_review_diff) })}
                  </Typography>
                  <Typography sx={{ color: semanticColor(comp.delta.unknown_internal_code_diff, true) }}>
                    {t('compare_many.delta_unknown', { value: signedValue(comp.delta.unknown_internal_code_diff) })}
                  </Typography>
                  <Typography>{t('compare_many.delta_total_qty', { value: signedValue(comp.delta.total_quantity_diff) })}</Typography>
                  <Typography>
                    {t('compare_many.delta_consolidated', { value: signedValue(comp.delta.consolidated_positions_diff) })}
                  </Typography>
                  {comp.delta.execution_time_delta != null ? (
                    <Typography sx={{ color: semanticColor(comp.delta.execution_time_delta, true) }}>
                      {t('compare_many.delta_execution_time', {
                        value: formatSignedDurationHuman(comp.delta.execution_time_delta),
                      })}
                    </Typography>
                  ) : null}
                </Box>

                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                  {t('compare_many.diff_summary_stats', {
                    onlyBaseline: comp.diff_summary.keys_only_in_a,
                    onlyTarget: comp.diff_summary.keys_only_in_b,
                    both: comp.diff_summary.keys_in_both,
                    qty: comp.diff_summary.quantity_changed,
                    sku: comp.diff_summary.sku_changed,
                    pos: comp.diff_summary.position_code_changed,
                  })}
                </Typography>
                {insightLine ? (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                    {insightLine}
                  </Typography>
                ) : null}

                {noDifferences ? (
                  <Alert severity="success" sx={{ mt: 1 }}>
                    {t('compare_many.no_differences')}
                  </Alert>
                ) : null}

                {expanded ? (
                  <Box sx={{ mt: 2 }} data-testid="compare-many-diff-rows-panel">
                    {diffRowsLoading ? <Typography>{t('compare_many.loading_diff_rows')}</Typography> : null}
                    {!diffRowsLoading ? (
                      <Box sx={{ overflowX: 'auto' }}>
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
                            {comp.diff_rows.map((row) => (
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
                      </Box>
                    ) : null}
                    {!diffRowsLoading && comp.diff_rows.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        {t('compare.no_diff_rows')}
                      </Typography>
                    ) : null}
                  </Box>
                ) : null}
              </Paper>
            );
          })}
        </Box>
      ) : null}
    </>
  );
}
