import type { AisleBenchmarkCompareResponse, JobSummary } from '../../../api/types';

export type CompareRunsDraftJobs = {
  jobA: string;
  jobB: string;
};

export function buildCompareRunsDraftSourceKey(aisleId: string, jobAId: string, jobBId: string): string {
  return `${aisleId}|${jobAId}|${jobBId}`;
}

export function buildCompareRunsDefaultDraftJobs(jobAId: string, jobBId: string, jobs: JobSummary[]): CompareRunsDraftJobs {
  if (jobAId || jobBId) {
    return { jobA: jobAId, jobB: jobBId };
  }
  if (jobs.length < 2) {
    return { jobA: '', jobB: '' };
  }
  const jobA = jobs[0]?.id ?? '';
  const jobB = jobs.find((j) => j.id !== jobA)?.id ?? '';
  return { jobA, jobB };
}

export function buildCompareRunsTitleSuffix(jobAId: string, jobBId: string): string {
  if (!jobAId || !jobBId) return '';
  return `${jobAId.slice(0, 8)}… vs ${jobBId.slice(0, 8)}…`;
}

export function computeBenchmarkWallClockDelta(compareData: AisleBenchmarkCompareResponse | undefined): number | null {
  if (!compareData) return null;
  const a = compareData.run_a.execution_time_seconds;
  const b = compareData.run_b.execution_time_seconds;
  if (a == null || b == null) return null;
  return b - a;
}
