import type { TFunction } from 'i18next';

export type AnalyticsCostWarningSeverity = 'info' | 'warning';

export interface AnalyticsCostWarningModel {
  code: string;
  label: string;
  severity: AnalyticsCostWarningSeverity;
}

const WARNING_SEVERITY: Record<string, AnalyticsCostWarningSeverity> = {
  COUNTED_QUANTITY_IS_OPERATIONAL_CURRENT_STATE: 'info',
  PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE: 'info',
  PROVIDER_MODEL_QUANTITY_DENOMINATOR_NOT_ATTRIBUTABLE: 'info',
  COST_SNAPSHOT_MISSING_FOR_SOME_JOBS: 'warning',
  PARTIAL_COST_CAPTURE_PRESENT: 'warning',
  LEGACY_JOBS_WITHOUT_COST: 'warning',
  COST_PER_UNIT_NOT_AVAILABLE: 'warning',
  COUNTED_QUANTITY_NOT_AVAILABLE: 'warning',
  COUNTED_QUANTITY_SCOPE_CAPPED: 'warning',
  COUNTED_QUANTITY_PARTIAL_NOT_RETURNED: 'warning',
  INVALID_COMPUTED_COST_PRESENT: 'warning',
  DATE_RANGE_CAPPED: 'warning',
  DATE_RANGE_CREATED_AT_PREFILTER_APPLIED: 'warning',
};

export function mapCostWarnings(codes: readonly string[], t: TFunction): AnalyticsCostWarningModel[] {
  const seen = new Set<string>();
  const out: AnalyticsCostWarningModel[] = [];
  for (const code of codes) {
    if (!code || seen.has(code)) continue;
    seen.add(code);
    const key = `analyticsDashboard.costWarnings.${code}`;
    const translated = t(key);
    out.push({
      code,
      label: translated === key ? t('analyticsDashboard.costWarnings.unknown', { code }) : translated,
      severity: WARNING_SEVERITY[code] ?? 'warning',
    });
  }
  return out;
}
