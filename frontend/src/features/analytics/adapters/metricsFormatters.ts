import type { TFunction } from 'i18next';
import i18n from '../../../i18n';

export function defaultDateRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - 30);
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

export function formatPct(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return i18n.t('common.em_dash');
  return `${(x * 100).toFixed(1)}%`;
}

export function formatAvgProcessingSec(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return i18n.t('common.em_dash');
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${(sec / 60).toFixed(1)} min`;
}

export function formatAvgProcessingMinutes(
  minutes: number | null | undefined,
  seconds: number | null | undefined
): string {
  if (minutes != null && !Number.isNaN(minutes)) return `${minutes.toFixed(1)} min`;
  return formatAvgProcessingSec(seconds);
}

export function numberOrZero(value: number | null | undefined): number {
  return value ?? 0;
}

export function paginateRows<T>(rows: readonly T[], page: number, pageSize: number): readonly T[] {
  const start = (page - 1) * pageSize;
  return rows.slice(start, start + pageSize);
}

export function compareValues(a: number | string | null | undefined, b: number | string | null | undefined): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

export function qualityPriority(label: string): number {
  const normalized = label.trim().toLowerCase();
  if (normalized === 'unidentified product') return 0;
  if (normalized === 'pending review') return 1;
  if (normalized === 'invalid traceability') return 2;
  if (normalized === 'missing evidence') return 3;
  if (normalized.includes('zero')) return 4;
  if (normalized === 'low confidence') return 5;
  if (normalized === 'no primary issue') return 6;
  return 50;
}

export function interventionLabel(category: string, t: TFunction): string {
  switch (category) {
    case 'confirmed':
      return t('analytics.category_confirmed');
    case 'qty_corrected':
      return t('analytics.category_qty_corrected');
    case 'sku_corrected':
      return t('analytics.category_sku_corrected');
    case 'invalid':
      return t('analytics.category_invalid');
    case 'operator_marked_unknown':
      return t('analytics.category_operator_unknown');
    case 'deleted':
      return t('analytics.category_deleted');
    default:
      return category;
  }
}

export function interventionPriority(category: string): number {
  switch (category) {
    case 'operator_marked_unknown':
      return 0;
    case 'qty_corrected':
      return 1;
    case 'sku_corrected':
      return 2;
    case 'confirmed':
      return 3;
    case 'deleted':
      return 4;
    case 'invalid':
      return 5;
    default:
      return 50;
  }
}

export function interventionColor(category: string): string {
  switch (category) {
    case 'operator_marked_unknown':
      return 'warning.main';
    case 'qty_corrected':
    case 'sku_corrected':
      return 'secondary.main';
    case 'confirmed':
      return 'success.main';
    case 'deleted':
      return 'text.secondary';
    default:
      return 'primary.main';
  }
}

export function translateQualityIssueType(issueType: string, t: TFunction): string {
  const slug = issueType
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  const key = `analytics.quality_issue.${slug}`;
  const translated = t(key);
  return translated === key ? issueType : translated;
}
