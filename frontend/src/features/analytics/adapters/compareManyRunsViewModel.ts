import type { TFunction } from 'i18next';
import type { AisleBenchmarkCompareManyResponse, BenchmarkCompareManyDiff, JobSummary } from '../../../api/types';
import { MAX_COMPARE_JOBS, MIN_COMPARE_JOBS } from '../constants/compareManyRuns';
import { formatSignedDurationHuman, wallClockSecondsFromJobTimestamps } from '../../../utils/benchmarkExecutionTime';

export type AppliedState = {
  aisleId: string;
  jobIds: string[];
  baseline: string;
};

export function parseJobIds(raw: string | null): string[] {
  if (!raw) return [];
  const out: string[] = [];
  for (const token of raw.split(',')) {
    const trimmed = token.trim();
    if (!trimmed) continue;
    out.push(trimmed);
  }
  return out;
}

export function parseAppliedState(searchParams: URLSearchParams): AppliedState {
  return {
    aisleId: searchParams.get('aisleId')?.trim() ?? '',
    jobIds: parseJobIds(searchParams.get('jobIds')),
    baseline: searchParams.get('baseline')?.trim() ?? '',
  };
}

export function isAppliedStateValid(state: AppliedState): boolean {
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

export function sameSelection(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id, idx) => id === b[idx]);
}

export function orderJobsForDisplay(jobIds: string[], baseline: string): string[] {
  const rest = jobIds.filter((id) => id !== baseline);
  return baseline ? [baseline, ...rest] : jobIds;
}

export function hasNoDifferences(comp: BenchmarkCompareManyDiff): boolean {
  const s = comp.diff_summary;
  return (
    s.keys_only_in_a === 0 &&
    s.keys_only_in_b === 0 &&
    s.quantity_changed === 0 &&
    s.sku_changed === 0 &&
    s.position_code_changed === 0
  );
}

export function compareManyExecutionInsight(t: TFunction, comp: BenchmarkCompareManyDiff): string | null {
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

export function sortJobsForCompareManyPicker(jobs: JobSummary[]): JobSummary[] {
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
}

export function buildJobsById(
  effectiveData: AisleBenchmarkCompareManyResponse | undefined
): Map<string, AisleBenchmarkCompareManyResponse['jobs'][number]> {
  return new Map((effectiveData?.jobs ?? []).map((job) => [job.job_id, job]));
}

export function buildOrderedComparisons(
  effectiveData: AisleBenchmarkCompareManyResponse | undefined,
  orderedJobIds: string[]
): BenchmarkCompareManyDiff[] {
  return (effectiveData?.comparisons ?? []).slice().sort((a, b) => {
    return orderedJobIds.indexOf(a.target_job_id) - orderedJobIds.indexOf(b.target_job_id);
  });
}
