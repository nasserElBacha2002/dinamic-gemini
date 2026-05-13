import type { TFunction } from 'i18next';
import type { BenchmarkRunCompareSide, JobSummary, LlmCostSnapshot } from '../../../api/types';
import { formatCostDisplay } from './compareFormatters';
import {
  formatExecutionDurationHuman,
  wallClockSecondsFromJobTimestamps,
} from '../../../utils/benchmarkExecutionTime';

export type RunModelFields = {
  provider_name?: string | null;
  model_name?: string | null;
};

/** Human-readable provider + model (compare-many cards, pickers). */
export function getRunModelLabel(run: RunModelFields, t: TFunction): string {
  const provider = (run.provider_name ?? '').trim() || t('compare_many.unknown_provider');
  const model = (run.model_name ?? '').trim() || t('compare_many.unknown_model');
  return `${provider} · ${model}`;
}

function snapshotForCostDisplay(run: {
  model_name?: string | null;
  llm_cost_snapshot?: LlmCostSnapshot | null;
}): Parameters<typeof formatCostDisplay>[0] {
  return {
    model_name: run.model_name,
    llm_cost_snapshot: run.llm_cost_snapshot
      ? {
          billing_currency: run.llm_cost_snapshot.billing_currency,
          pricing_available: run.llm_cost_snapshot.pricing_available,
          model: run.llm_cost_snapshot.model,
          computed_cost: run.llm_cost_snapshot.computed_cost
            ? {
                total_cost: run.llm_cost_snapshot.computed_cost.total_cost,
                currency: run.llm_cost_snapshot.computed_cost.currency,
                total_cost_unavailable_reason:
                  run.llm_cost_snapshot.computed_cost.total_cost_unavailable_reason,
              }
            : undefined,
          capture_status: run.llm_cost_snapshot.capture_status,
          capture_notes: run.llm_cost_snapshot.capture_notes,
        }
      : null,
  };
}

/** Single-line cost for dropdowns / metadata. */
export function getRunCostSummaryLine(
  run: { model_name?: string | null; llm_cost_snapshot?: LlmCostSnapshot | null },
  t: TFunction
): string {
  if (!run.llm_cost_snapshot) {
    return t('compare_many.cost_unavailable');
  }
  const total = run.llm_cost_snapshot.computed_cost?.total_cost?.trim();
  if (!total) {
    return t('compare_many.cost_unavailable');
  }
  return formatCostDisplay(snapshotForCostDisplay(run), t).value;
}

/** Card / list line: "Costo: …" with Spanish label from compare_many.* */
export function getRunCostCardLine(
  run: { model_name?: string | null; llm_cost_snapshot?: LlmCostSnapshot | null },
  t: TFunction
): string {
  if (!run.llm_cost_snapshot || !run.llm_cost_snapshot.computed_cost?.total_cost?.trim()) {
    return t('compare_many.cost_line', { value: t('compare_many.cost_unavailable') });
  }
  const { value } = formatCostDisplay(snapshotForCostDisplay(run), t);
  return t('compare_many.cost_line', { value });
}

export function jobSummaryExecutionPreview(job: JobSummary): string | null {
  const secs = wallClockSecondsFromJobTimestamps(job.started_at, job.finished_at);
  if (secs == null) return null;
  return formatExecutionDurationHuman(secs);
}

/** Secondary line for compare-many run pickers: job id, status, cost, optional duration. */
export function getRunPickerMenuSecondaryLine(job: JobSummary, t: TFunction): string {
  const parts: string[] = [];
  parts.push(t('compare_many.job_id_short', { id: job.id.slice(0, 8) }));
  parts.push(t('compare_many.status_inline', { status: job.status }));
  parts.push(getRunCostSummaryLine(job, t));
  const dur = jobSummaryExecutionPreview(job);
  if (dur) {
    parts.push(t('compare_many.exec_inline', { value: dur }));
  }
  return parts.join(' · ');
}

export function formatBaselineVsTargetFromRuns(
  baselineJobId: string,
  targetJobId: string,
  jobsById: Map<string, BenchmarkRunCompareSide>,
  t: TFunction
): string {
  const b = jobsById.get(baselineJobId);
  const tg = jobsById.get(targetJobId);
  const bLabel = b ? getRunModelLabel(b, t) : baselineJobId.slice(0, 8);
  const tLabel = tg ? getRunModelLabel(tg, t) : targetJobId.slice(0, 8);
  return t('compare_many.baseline_vs_target', { baseline: bLabel, target: tLabel });
}
