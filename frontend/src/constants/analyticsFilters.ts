import { defaultDateRange } from '../features/analytics/adapters/metricsFormatters';
import type { AnalyticsDashboardFilters } from '../features/analytics-dashboard/types';

export const ANALYTICS_FILTER_QUERY_KEYS = {
  dateFrom: 'date_from',
  dateTo: 'date_to',
  inventoryId: 'inventory_id',
  aisleId: 'aisle_id',
  clientId: 'client_id',
  clientSupplierId: 'client_supplier_id',
  providerName: 'provider_name',
  modelName: 'model_name',
} as const;

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function createDefaultAnalyticsFilters(): AnalyticsDashboardFilters {
  const range = defaultDateRange();
  return {
    dateFrom: range.from,
    dateTo: range.to,
    inventoryId: '',
    aisleId: '',
    clientId: '',
    clientSupplierId: '',
    providerName: '',
    modelName: '',
  };
}

function trimParam(value: string | null): string {
  return (value ?? '').trim();
}

function parseDateParam(value: string | null, fallback: string): string {
  const raw = trimParam(value);
  if (!raw || !DATE_PATTERN.test(raw)) {
    return fallback;
  }
  const parsed = Date.parse(`${raw}T00:00:00.000Z`);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return raw;
}

export function areAnalyticsFiltersEqual(
  a: AnalyticsDashboardFilters,
  b: AnalyticsDashboardFilters
): boolean {
  return (
    a.dateFrom === b.dateFrom &&
    a.dateTo === b.dateTo &&
    a.inventoryId === b.inventoryId &&
    a.aisleId === b.aisleId &&
    a.clientId === b.clientId &&
    a.clientSupplierId === b.clientSupplierId &&
    a.providerName === b.providerName &&
    a.modelName === b.modelName
  );
}

export function normalizeAnalyticsFilters(
  filters: AnalyticsDashboardFilters,
  defaults: AnalyticsDashboardFilters = createDefaultAnalyticsFilters()
): AnalyticsDashboardFilters {
  let dateFrom = parseDateParam(filters.dateFrom, defaults.dateFrom);
  let dateTo = parseDateParam(filters.dateTo, defaults.dateTo);
  if (dateFrom > dateTo) {
    dateFrom = defaults.dateFrom;
    dateTo = defaults.dateTo;
  }

  const inventoryId = trimParam(filters.inventoryId);
  let aisleId = trimParam(filters.aisleId);
  if (!inventoryId) {
    aisleId = '';
  }

  return {
    dateFrom,
    dateTo,
    inventoryId,
    aisleId,
    clientId: trimParam(filters.clientId),
    clientSupplierId: trimParam(filters.clientSupplierId),
    providerName: trimParam(filters.providerName),
    modelName: trimParam(filters.modelName),
  };
}

export function parseAnalyticsFiltersFromSearchParams(
  params: URLSearchParams,
  defaults: AnalyticsDashboardFilters
): AnalyticsDashboardFilters {
  return normalizeAnalyticsFilters(
    {
      dateFrom: parseDateParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.dateFrom), defaults.dateFrom),
      dateTo: parseDateParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.dateTo), defaults.dateTo),
      inventoryId: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.inventoryId)),
      aisleId: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.aisleId)),
      clientId: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.clientId)),
      clientSupplierId: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.clientSupplierId)),
      providerName: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.providerName)),
      modelName: trimParam(params.get(ANALYTICS_FILTER_QUERY_KEYS.modelName)),
    },
    defaults
  );
}

function setFilterParam(next: URLSearchParams, key: string, value: string): void {
  const trimmed = value.trim();
  if (!trimmed) {
    next.delete(key);
    return;
  }
  next.set(key, trimmed);
}

/**
 * Serialize filters into the query string.
 * Dates are always written when present (shareable / stable across calendar days).
 * Empty strings are omitted; unknown params on `params` are preserved.
 */
export function writeAnalyticsFiltersToSearchParams(
  params: URLSearchParams,
  filters: AnalyticsDashboardFilters,
  defaults: AnalyticsDashboardFilters
): URLSearchParams {
  const next = new URLSearchParams(params);
  const normalized = normalizeAnalyticsFilters(filters, defaults);

  for (const key of Object.values(ANALYTICS_FILTER_QUERY_KEYS)) {
    next.delete(key);
  }

  // Visible dates must always be shareable — do not omit when equal to session defaults.
  if (normalized.dateFrom) {
    next.set(ANALYTICS_FILTER_QUERY_KEYS.dateFrom, normalized.dateFrom);
  }
  if (normalized.dateTo) {
    next.set(ANALYTICS_FILTER_QUERY_KEYS.dateTo, normalized.dateTo);
  }

  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.inventoryId, normalized.inventoryId);
  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.aisleId, normalized.aisleId);
  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.clientId, normalized.clientId);
  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.clientSupplierId, normalized.clientSupplierId);
  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.providerName, normalized.providerName);
  setFilterParam(next, ANALYTICS_FILTER_QUERY_KEYS.modelName, normalized.modelName);

  return next;
}

export function clearAnalyticsFilterSearchParams(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of Object.values(ANALYTICS_FILTER_QUERY_KEYS)) {
    next.delete(key);
  }
  return next;
}

export function analyticsSearchParamsEqual(a: URLSearchParams, b: URLSearchParams): boolean {
  const entriesA = [...a.entries()].sort(([ka], [kb]) => ka.localeCompare(kb));
  const entriesB = [...b.entries()].sort(([ka], [kb]) => ka.localeCompare(kb));
  if (entriesA.length !== entriesB.length) return false;
  return entriesA.every(([key, value], index) => {
    const [otherKey, otherValue] = entriesB[index] ?? [];
    return key === otherKey && value === otherValue;
  });
}

/** Spec aliases — same contract as `*FromSearchParams` / `*ToSearchParams`. */
export const parseAnalyticsFilters = parseAnalyticsFiltersFromSearchParams;
export const writeAnalyticsFilters = writeAnalyticsFiltersToSearchParams;
export const getDefaultAnalyticsFilters = createDefaultAnalyticsFilters;
