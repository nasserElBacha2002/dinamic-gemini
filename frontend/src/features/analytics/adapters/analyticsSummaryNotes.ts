import type { TFunction } from 'i18next';

/** Backend sends fixed English strings; map to i18n keys for Spanish UI. */
const EN_TO_KEY: Record<string, string> = {
  'Current-state metrics use entity scope; review-action date filters apply to review KPIs; average processing time and job success rate use job timestamps (finished_at / updated_at) in range.':
    'analytics.summary_note_scope_sql',
  'Current-state metrics use entity scope; date filters apply only to review-action and job-based metrics.':
    'analytics.summary_note_scope_memory',
  'Date range open-ended: settling_actions_per_day uses a 1-day divisor; set date_from and date_to for meaningful per-day rates.':
    'analytics.summary_note_open_date_range',
  'Multi-run: position totals count every persisted row in scope, not only the operational or single-resolved slice shown on Aisle Results. Do not compare 1:1 with per-run browsing.':
    'analytics.summary_note_multi_run',
};

export function localizeAnalyticsSummaryNote(note: string, t: TFunction): string {
  const key = EN_TO_KEY[note.trim()];
  if (key) return t(key);
  return note;
}
