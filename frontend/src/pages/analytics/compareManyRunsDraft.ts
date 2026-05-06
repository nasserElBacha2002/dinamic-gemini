/** Draft validation for compare-many URL/UI state (shared with page + tests). */

import { MAX_COMPARE_JOBS, MIN_COMPARE_JOBS } from '../../features/analytics/constants/compareManyRuns';

export function buildDraftError(
  aisleId: string,
  jobIds: string[],
  baseline: string,
  t: (key: string) => string
): string | null {
  if (new Set(jobIds).size !== jobIds.length) return t('compare_many.errors.duplicate_jobs');
  if (!aisleId) return t('compare_many.errors.select_aisle');
  if (jobIds.length < MIN_COMPARE_JOBS) return t('compare_many.errors.pick_two_jobs');
  if (jobIds.length > MAX_COMPARE_JOBS) return t('compare_many.errors.pick_max_three_jobs');
  if (!baseline || !jobIds.includes(baseline)) return t('compare_many.errors.pick_valid_baseline');
  return null;
}
