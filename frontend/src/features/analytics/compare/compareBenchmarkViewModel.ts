import type { TFunction } from 'i18next';
import type {
  AisleBenchmarkCompareManyResponse,
  BenchmarkCompareManyDiff,
  BenchmarkRunCompareSide,
  LlmCostSnapshot,
} from '../../../api/types';
import type { BarChartDatum } from '../../analytics-dashboard/adapters/analyticsChartDatasets';
import { compareRunExecutionLabel, formatCostDisplay, signedValue } from '../adapters/compareFormatters';
import { formatExecutionDurationHuman, formatSignedDurationHuman } from '../../../utils/benchmarkExecutionTime';
import { getJobStatusLabel } from '../../../utils/jobStatus';
import { getRunModelLabel } from '../adapters/compareRunLabels';

const SUMMABLE_CAPTURE_STATUSES = new Set<LlmCostSnapshot['capture_status']>([
  'exact',
  'estimated',
  'partial',
]);

export type CompareDeltaTone = 'positive' | 'negative' | 'neutral' | 'warning';

export interface CompareDeltaKpi {
  id: string;
  label: string;
  value: string;
  helper?: string;
  tone: CompareDeltaTone;
}

export interface CompareExecutiveSummaryModel {
  title: string;
  baselineLabel: string;
  baselineValue: string;
  comparedRunsLabel: string;
  comparedRunsValue: string;
  selectedRunsCostLabel: string;
  selectedRunsCostValue: string;
  costRangeLabel: string;
  costRangeValue: string;
  timeRangeLabel: string;
  timeRangeValue: string;
  quantityRangeLabel: string;
  quantityRangeValue: string;
  jobsWithCostLabel: string;
  jobsWithCostValue: string;
  jobsWithoutCostLabel: string;
  jobsWithoutCostValue: string;
  mixedCurrencyHelper: string | null;
}

export interface CompareRunBenchmarkCardModel {
  jobId: string;
  isBaseline: boolean;
  providerModelLabel: string;
  baselineChipLabel: string;
  statusLabel: string;
  runCostLabel: string;
  runCostValue: string;
  runCostDetails: string | null;
  costPerUnitLabel: string;
  costPerUnitValue: string;
  costPerUnitHelper: string;
  executionTimeLabel: string;
  executionTimeValue: string;
  quantityLabel: string;
  quantityValue: string;
  reviewRequiredLabel: string;
  reviewRequiredValue: string;
  unknownCodesLabel: string;
  unknownCodesValue: string;
  consolidatedLabel: string;
  consolidatedValue: string;
  costCaptureStatusLabel: string;
  costCaptureStatusValue: string;
}

export interface CompareTargetDeltaRowModel {
  targetJobId: string;
  title: string;
  kpis: CompareDeltaKpi[];
}

export interface CompareDifferenceSummaryModel {
  title: string;
  skuDiffLabel: string;
  skuDiffValue: string;
  quantityDiffLabel: string;
  quantityDiffValue: string;
  positionDiffLabel: string;
  positionDiffValue: string;
  onlyBaselineLabel: string;
  onlyBaselineValue: string;
  onlyTargetLabel: string;
  onlyTargetValue: string;
  truncatedWarning: string | null;
  expandHint: string | null;
}

export interface CompareBenchmarkChartsModel {
  costPerRun: { title: string; emptyText: string; data: BarChartDatum[] };
  costPerUnit: { title: string; subtitle: string; emptyText: string; data: BarChartDatum[] };
  executionTime: { title: string; emptyText: string; data: BarChartDatum[] };
  quantity: { title: string; subtitle: string; emptyText: string; data: BarChartDatum[] };
  reviewRequired: { title: string; subtitle: string; emptyText: string; data: BarChartDatum[] };
  unknownCodes: { title: string; emptyText: string; data: BarChartDatum[] };
}

function parseCostAmount(snapshot: LlmCostSnapshot | null | undefined): number | null {
  if (!snapshot) return null;
  if (!SUMMABLE_CAPTURE_STATUSES.has(snapshot.capture_status)) return null;
  const totalRaw = snapshot.computed_cost?.total_cost?.trim();
  if (!totalRaw) {
    if (status === 'partial') {
      const partial = snapshot.computed_cost?.partial_total_cost?.trim();
      if (!partial) return null;
      const partialN = Number.parseFloat(partial);
      return Number.isFinite(partialN) && partialN >= 0 ? partialN : null;
    }
    return null;
  }
  const n = Number.parseFloat(totalRaw);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

export function hasValidRunCost(job: BenchmarkRunCompareSide): boolean {
  return parseCostAmount(job.llm_cost_snapshot) != null;
}

export function getRunCostPerUnitAmount(job: BenchmarkRunCompareSide): number | null {
  const cost = parseCostAmount(job.llm_cost_snapshot);
  const qty = job.metrics.total_quantity;
  if (cost == null || !Number.isFinite(qty) || qty <= 0) return null;
  return cost / qty;
}

export function formatRunCostPerUnit(job: BenchmarkRunCompareSide, t: TFunction): string {
  const amount = getRunCostPerUnitAmount(job);
  if (amount == null) return t('compare_many.benchmark.notAvailable');
  const currency =
    job.llm_cost_snapshot?.computed_cost?.currency?.trim() ||
    job.llm_cost_snapshot?.billing_currency?.trim() ||
    '';
  const formatted = amount.toFixed(6).replace(/\.?0+$/, '');
  return currency ? `${formatted} ${currency}` : formatted;
}

function runChartLabel(job: BenchmarkRunCompareSide, t: TFunction): string {
  return getRunModelLabel(job, t);
}

function deltaToneLowerIsBetter(value: number): CompareDeltaTone {
  if (value === 0) return 'neutral';
  return value < 0 ? 'positive' : 'negative';
}

function deltaToneNeutral(): CompareDeltaTone {
  return 'neutral';
}

function deltaToneReview(value: number): CompareDeltaTone {
  if (value === 0) return 'neutral';
  if (value < 0) return 'positive';
  return 'warning';
}

function formatCostDelta(value: number | null): string {
  if (value == null) return '';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(6).replace(/\.?0+$/, '')}`;
}

function formatCostNumber(value: number): string {
  return value.toFixed(6).replace(/\.?0+$/, '');
}

function snapshotCurrency(snapshot: LlmCostSnapshot): string | null {
  const currency = snapshot.computed_cost?.currency?.trim() || snapshot.billing_currency?.trim();
  return currency || null;
}

type CostCurrencySummary =
  | { kind: 'none' }
  | { kind: 'mixed' }
  | { kind: 'single'; currency: string | null; amounts: number[] };

function summarizeRunCosts(jobs: BenchmarkRunCompareSide[]): CostCurrencySummary {
  const entries: { amount: number; currency: string | null }[] = [];
  for (const job of jobs) {
    const snap = job.llm_cost_snapshot;
    if (!snap) continue;
    const amount = parseCostAmount(snap);
    if (amount == null) continue;
    entries.push({ amount, currency: snapshotCurrency(snap) });
  }
  if (entries.length === 0) return { kind: 'none' };

  const definedCurrencies = new Set(
    entries.map((e) => e.currency).filter((c): c is string => Boolean(c))
  );
  if (definedCurrencies.size > 1) return { kind: 'mixed' };

  const hasMissingCurrency = entries.some((e) => !e.currency);
  const hasDefinedCurrency = entries.some((e) => Boolean(e.currency));
  if (hasMissingCurrency && hasDefinedCurrency) return { kind: 'mixed' };

  return {
    kind: 'single',
    currency: definedCurrencies.size === 1 ? [...definedCurrencies][0]! : null,
    amounts: entries.map((e) => e.amount),
  };
}

function formatCostWithOptionalCurrency(value: number, currency: string | null): string {
  const formatted = formatCostNumber(value);
  return currency ? `${formatted} ${currency}` : formatted;
}

function costCaptureStatusLabel(job: BenchmarkRunCompareSide, t: TFunction): string {
  const snap = job.llm_cost_snapshot;
  if (!snap) return t('compare.llm_cost_status.unavailable');
  return t(`compare.llm_cost_status.${snap.capture_status ?? 'unavailable'}`, {
    defaultValue: t('compare.llm_cost_status.unavailable'),
  });
}

export function buildCompareExecutiveSummary(
  data: AisleBenchmarkCompareManyResponse,
  t: TFunction
): CompareExecutiveSummaryModel {
  const jobs = data.jobs ?? [];
  const costSummary = summarizeRunCosts(jobs);
  const withCost = jobs.filter((j) => hasValidRunCost(j)).length;
  const withoutCost = jobs.length - withCost;

  let selectedRunsCostValue = t('compare_many.benchmark.notAvailable');
  let costRangeValue = t('compare_many.benchmark.notAvailable');
  let mixedCurrencyHelper: string | null = null;

  if (costSummary.kind === 'mixed') {
    mixedCurrencyHelper = t('compare_many.benchmark.mixedCurrencyHelper');
  } else if (costSummary.kind === 'single') {
    const total = costSummary.amounts.reduce((a, b) => a + b, 0);
    const minCost = Math.min(...costSummary.amounts);
    const maxCost = Math.max(...costSummary.amounts);
    selectedRunsCostValue = formatCostWithOptionalCurrency(total, costSummary.currency);
    costRangeValue = `${formatCostWithOptionalCurrency(minCost, costSummary.currency)} – ${formatCostWithOptionalCurrency(maxCost, costSummary.currency)}`;
  }

  const qtys = jobs.map((j) => j.metrics.total_quantity).filter((q) => Number.isFinite(q));
  const minQty = qtys.length ? Math.min(...qtys) : null;
  const maxQty = qtys.length ? Math.max(...qtys) : null;

  const baselineJob = jobs.find((j) => j.job_id === data.baseline_job_id);

  return {
    title: t('compare_many.benchmark.executiveSummary'),
    baselineLabel: t('compare_many.benchmark.baselineRun'),
    baselineValue: baselineJob ? getRunModelLabel(baselineJob, t) : data.baseline_job_id.slice(0, 8),
    comparedRunsLabel: t('compare_many.benchmark.comparedRunsCount'),
    comparedRunsValue: String(data.summary.job_count),
    selectedRunsCostLabel: t('compare_many.benchmark.selectedRunsCost'),
    selectedRunsCostValue,
    costRangeLabel: t('compare_many.benchmark.costRange'),
    costRangeValue,
    timeRangeLabel: t('compare_many.benchmark.timeRange'),
    timeRangeValue:
      data.summary.min_execution_time_seconds != null && data.summary.max_execution_time_seconds != null
        ? `${formatExecutionDurationHuman(data.summary.min_execution_time_seconds)} – ${formatExecutionDurationHuman(data.summary.max_execution_time_seconds)}`
        : t('compare_many.summary_exec_unavailable'),
    quantityRangeLabel: t('compare_many.benchmark.quantityRange'),
    quantityRangeValue:
      minQty != null && maxQty != null ? `${minQty} – ${maxQty}` : t('compare_many.benchmark.notAvailable'),
    jobsWithCostLabel: t('compare_many.benchmark.jobsWithCost'),
    jobsWithCostValue: String(withCost),
    jobsWithoutCostLabel: t('compare_many.benchmark.jobsWithoutCost'),
    jobsWithoutCostValue: String(withoutCost),
    mixedCurrencyHelper,
  };
}

export function buildRunBenchmarkCards(
  data: AisleBenchmarkCompareManyResponse,
  orderedJobIds: string[],
  t: TFunction
): CompareRunBenchmarkCardModel[] {
  const jobsById = new Map((data.jobs ?? []).map((j) => [j.job_id, j]));
  return orderedJobIds
    .map((jobId) => {
      const job = jobsById.get(jobId);
      if (!job) return null;
      const costDisplay = formatCostDisplay(
        { model_name: job.model_name, llm_cost_snapshot: job.llm_cost_snapshot ?? null },
        t
      );
      return {
        jobId,
        isBaseline: jobId === data.baseline_job_id,
        providerModelLabel: getRunModelLabel(job, t),
        baselineChipLabel: t('compare_many.baseline_chip'),
        statusLabel: t('compare_many.status_chip', { status: getJobStatusLabel(job.status) }),
        runCostLabel: t('compare_many.benchmark.costPerRun'),
        runCostValue: costDisplay.value,
        runCostDetails: costDisplay.details,
        costPerUnitLabel: t('compare_many.benchmark.costPerUnitPerRun'),
        costPerUnitValue: formatRunCostPerUnit(job, t),
        costPerUnitHelper: t('compare_many.benchmark.costPerUnitHelper'),
        executionTimeLabel: t('compare_many.benchmark.executionTimeLabel'),
        executionTimeValue: compareRunExecutionLabel(job, t),
        quantityLabel: t('compare_many.benchmark.quantityPerRun'),
        quantityValue: String(job.metrics.total_quantity),
        reviewRequiredLabel: t('compare_many.benchmark.reviewRequiredPerRun'),
        reviewRequiredValue: String(job.metrics.needs_review_count),
        unknownCodesLabel: t('compare_many.benchmark.unknownCodesPerRun'),
        unknownCodesValue: String(job.metrics.unknown_internal_code_count),
        consolidatedLabel: t('compare_many.benchmark.consolidatedPerRun'),
        consolidatedValue: String(job.metrics.consolidated_positions),
        costCaptureStatusLabel: t('compare_many.benchmark.costSnapshotHelper'),
        costCaptureStatusValue: costCaptureStatusLabel(job, t),
      };
    })
    .filter((c): c is CompareRunBenchmarkCardModel => c != null);
}

export function buildDeltaKpiModels(
  data: AisleBenchmarkCompareManyResponse,
  jobsById: Map<string, BenchmarkRunCompareSide>,
  orderedComparisons: BenchmarkCompareManyDiff[],
  t: TFunction
): CompareTargetDeltaRowModel[] {
  const baselineJob = jobsById.get(data.baseline_job_id);
  const baselineCost = baselineJob ? parseCostAmount(baselineJob.llm_cost_snapshot) : null;
  const baselineCpu = baselineJob ? getRunCostPerUnitAmount(baselineJob) : null;

  return orderedComparisons.map((comp) => {
    const targetJob = jobsById.get(comp.target_job_id);
    const targetCost = targetJob ? parseCostAmount(targetJob.llm_cost_snapshot) : null;
    const targetCpu = targetJob ? getRunCostPerUnitAmount(targetJob) : null;

    const costDelta =
      baselineCost != null && targetCost != null ? targetCost - baselineCost : null;
    const cpuDelta = baselineCpu != null && targetCpu != null ? targetCpu - baselineCpu : null;

    const targetLabel = targetJob ? getRunModelLabel(targetJob, t) : comp.target_job_id.slice(0, 8);

    const kpis: CompareDeltaKpi[] = [
      {
        id: 'cost',
        label: t('compare_many.benchmark.deltaCost'),
        value:
          costDelta != null ? formatCostDelta(costDelta) : t('compare_many.benchmark.notAvailable'),
        tone: costDelta != null ? deltaToneLowerIsBetter(costDelta) : 'neutral',
      },
      {
        id: 'cost_per_unit',
        label: t('compare_many.benchmark.deltaCostPerUnit'),
        value: cpuDelta != null ? formatCostDelta(cpuDelta) : t('compare_many.benchmark.notAvailable'),
        tone: cpuDelta != null ? deltaToneLowerIsBetter(cpuDelta) : 'neutral',
        helper: t('compare_many.benchmark.costPerUnitHelper'),
      },
      {
        id: 'time',
        label: t('compare_many.benchmark.deltaTime'),
        value:
          comp.delta.execution_time_delta != null
            ? formatSignedDurationHuman(comp.delta.execution_time_delta)
            : t('compare_many.benchmark.notAvailable'),
        tone:
          comp.delta.execution_time_delta != null
            ? deltaToneLowerIsBetter(comp.delta.execution_time_delta)
            : 'neutral',
      },
      {
        id: 'quantity',
        label: t('compare_many.benchmark.deltaQuantity'),
        value: signedValue(comp.delta.total_quantity_diff),
        tone: deltaToneNeutral(),
        helper: t('compare_many.benchmark.neutralQuantityHelper'),
      },
      {
        id: 'review',
        label: t('compare_many.benchmark.deltaReviewRequired'),
        value: signedValue(comp.delta.needs_review_diff),
        tone: deltaToneReview(comp.delta.needs_review_diff),
        helper: t('compare_many.benchmark.contextualReviewHelper'),
      },
      {
        id: 'unknown',
        label: t('compare_many.benchmark.deltaUnknownCodes'),
        value: signedValue(comp.delta.unknown_internal_code_diff),
        tone: deltaToneLowerIsBetter(comp.delta.unknown_internal_code_diff),
      },
      {
        id: 'consolidated',
        label: t('compare_many.benchmark.deltaConsolidatedPositions'),
        value: signedValue(comp.delta.consolidated_positions_diff),
        tone: deltaToneNeutral(),
        helper: t('compare_many.benchmark.neutralQuantityHelper'),
      },
    ];

    return {
      targetJobId: comp.target_job_id,
      title: t('compare_many.baseline_vs_target', {
        baseline: baselineJob ? getRunModelLabel(baselineJob, t) : comp.baseline_job_id.slice(0, 8),
        target: targetLabel,
      }),
      kpis,
    };
  });
}

function buildBarData(
  jobs: BenchmarkRunCompareSide[],
  getValue: (job: BenchmarkRunCompareSide) => number | null,
  formatDisplay: (value: number, job: BenchmarkRunCompareSide) => string,
  t: TFunction
): BarChartDatum[] {
  return jobs
    .map((job) => {
      const value = getValue(job);
      if (value == null || !Number.isFinite(value) || value < 0) return null;
      return {
        id: job.job_id,
        label: runChartLabel(job, t),
        value,
        displayValue: formatDisplay(value, job),
      };
    })
    .filter((x): x is BarChartDatum => x != null);
}

export function buildCompareBenchmarkCharts(
  data: AisleBenchmarkCompareManyResponse,
  orderedJobIds: string[],
  t: TFunction
): CompareBenchmarkChartsModel {
  const jobs = orderedJobIds
    .map((id) => (data.jobs ?? []).find((j) => j.job_id === id))
    .filter((j): j is BenchmarkRunCompareSide => j != null);

  const emptyText = t('analyticsDashboard.visual.emptyChart');

  return {
    costPerRun: {
      title: t('compare_many.benchmark.costPerRun'),
      emptyText,
      data: buildBarData(
        jobs,
        (j) => parseCostAmount(j.llm_cost_snapshot),
        (v) => v.toFixed(6).replace(/\.?0+$/, ''),
        t
      ),
    },
    costPerUnit: {
      title: t('compare_many.benchmark.costPerUnitPerRun'),
      subtitle: t('compare_many.benchmark.costPerUnitHelper'),
      emptyText,
      data: buildBarData(jobs, (j) => getRunCostPerUnitAmount(j), (v) => v.toFixed(6).replace(/\.?0+$/, ''), t),
    },
    executionTime: {
      title: t('compare_many.benchmark.timePerRun'),
      emptyText,
      data: buildBarData(
        jobs,
        (j) => j.execution_time_seconds ?? null,
        (v, j) => compareRunExecutionLabel({ ...j, execution_time_seconds: v }, t),
        t
      ),
    },
    quantity: {
      title: t('compare_many.benchmark.quantityPerRun'),
      subtitle: t('compare_many.benchmark.neutralQuantityHelper'),
      emptyText,
      data: buildBarData(jobs, (j) => j.metrics.total_quantity, (v) => String(v), t),
    },
    reviewRequired: {
      title: t('compare_many.benchmark.reviewRequiredPerRun'),
      subtitle: t('compare_many.benchmark.contextualReviewHelper'),
      emptyText,
      data: buildBarData(jobs, (j) => j.metrics.needs_review_count, (v) => String(v), t),
    },
    unknownCodes: {
      title: t('compare_many.benchmark.unknownCodesPerRun'),
      emptyText,
      data: buildBarData(jobs, (j) => j.metrics.unknown_internal_code_count, (v) => String(v), t),
    },
  };
}

export function buildDifferenceSummary(
  comp: BenchmarkCompareManyDiff,
  hasDiffRowsLoaded: boolean,
  t: TFunction
): CompareDifferenceSummaryModel {
  const s = comp.diff_summary;
  return {
    title: t('compare_many.benchmark.differenceSummary'),
    skuDiffLabel: t('compare_many.benchmark.skuDifferences'),
    skuDiffValue: String(s.sku_changed),
    quantityDiffLabel: t('compare_many.benchmark.quantityDifferences'),
    quantityDiffValue: String(s.quantity_changed),
    positionDiffLabel: t('compare_many.benchmark.positionDifferences'),
    positionDiffValue: String(s.position_code_changed),
    onlyBaselineLabel: t('compare_many.benchmark.onlyBaseline'),
    onlyBaselineValue: String(s.keys_only_in_a),
    onlyTargetLabel: t('compare_many.benchmark.onlyTarget'),
    onlyTargetValue: String(s.keys_only_in_b),
    truncatedWarning: comp.diff_rows_truncated
      ? t('compare_many.benchmark.truncatedDiffWarning')
      : null,
    expandHint: !hasDiffRowsLoaded ? t('compare_many.benchmark.expandForDiffRows') : null,
  };
}
