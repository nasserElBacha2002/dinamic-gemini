/**
 * URL filter contract for processing observability tab (`tab=procesamiento`).
 */

import { DEFAULT_LIST_PAGE_SIZE, TABLE_PAGE_SIZE_OPTIONS } from '../../../constants/dataTable';

export const PROCESSING_TAB_QUERY_VALUE = 'procesamiento';

export const PROCESSING_FILTER_QUERY_KEYS = {
  tab: 'tab',
  assetId: 'assetId',
  status: 'status',
  strategy: 'strategy',
  resolvedBy: 'resolvedBy',
  search: 'search',
  page: 'page',
  hasWarnings: 'hasWarnings',
  hasFallback: 'hasFallback',
} as const;

export type ProcessingUrlFilters = {
  assetId: string;
  status: string;
  strategy: string;
  resolvedBy: string;
  search: string;
  page: number;
  hasWarnings: boolean | null;
  hasFallback: boolean | null;
};

export function createDefaultProcessingFilters(): ProcessingUrlFilters {
  return {
    assetId: '',
    status: '',
    strategy: '',
    resolvedBy: '',
    search: '',
    page: 1,
    hasWarnings: null,
    hasFallback: null,
  };
}

function trimParam(value: string | null): string {
  return (value ?? '').trim();
}

function parsePositiveInt(value: string | null, fallback: number): number {
  const raw = trimParam(value);
  if (!raw || !/^\d+$/.test(raw)) return fallback;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return fallback;
  return n;
}

function parseOptionalBool(value: string | null): boolean | null {
  const raw = trimParam(value).toLowerCase();
  if (raw === 'true' || raw === '1') return true;
  if (raw === 'false' || raw === '0') return false;
  return null;
}

export function normalizeProcessingFilters(filters: ProcessingUrlFilters): ProcessingUrlFilters {
  const defaults = createDefaultProcessingFilters();
  return {
    assetId: filters.assetId.trim(),
    status: filters.status.trim(),
    strategy: filters.strategy.trim(),
    resolvedBy: filters.resolvedBy.trim(),
    search: filters.search.trim(),
    page:
      Number.isFinite(filters.page) && filters.page >= 1 ? Math.floor(filters.page) : defaults.page,
    hasWarnings: filters.hasWarnings === true ? true : filters.hasWarnings === false ? false : null,
    hasFallback: filters.hasFallback === true ? true : filters.hasFallback === false ? false : null,
  };
}

export function parseProcessingFilters(
  params: URLSearchParams,
  defaults: ProcessingUrlFilters = createDefaultProcessingFilters()
): ProcessingUrlFilters {
  return normalizeProcessingFilters({
    assetId: trimParam(params.get(PROCESSING_FILTER_QUERY_KEYS.assetId)),
    status: trimParam(params.get(PROCESSING_FILTER_QUERY_KEYS.status)),
    strategy: trimParam(params.get(PROCESSING_FILTER_QUERY_KEYS.strategy)),
    resolvedBy: trimParam(params.get(PROCESSING_FILTER_QUERY_KEYS.resolvedBy)),
    search: trimParam(params.get(PROCESSING_FILTER_QUERY_KEYS.search)),
    page: parsePositiveInt(params.get(PROCESSING_FILTER_QUERY_KEYS.page), defaults.page),
    hasWarnings: parseOptionalBool(params.get(PROCESSING_FILTER_QUERY_KEYS.hasWarnings)),
    hasFallback: parseOptionalBool(params.get(PROCESSING_FILTER_QUERY_KEYS.hasFallback)),
  });
}

export function areProcessingFiltersEqual(a: ProcessingUrlFilters, b: ProcessingUrlFilters): boolean {
  const na = normalizeProcessingFilters(a);
  const nb = normalizeProcessingFilters(b);
  return (
    na.assetId === nb.assetId &&
    na.status === nb.status &&
    na.strategy === nb.strategy &&
    na.resolvedBy === nb.resolvedBy &&
    na.search === nb.search &&
    na.page === nb.page &&
    na.hasWarnings === nb.hasWarnings &&
    na.hasFallback === nb.hasFallback
  );
}

export function writeProcessingFilters(
  params: URLSearchParams,
  filters: ProcessingUrlFilters,
  defaults: ProcessingUrlFilters = createDefaultProcessingFilters()
): URLSearchParams {
  const next = new URLSearchParams(params);
  const normalized = normalizeProcessingFilters(filters);

  for (const key of Object.values(PROCESSING_FILTER_QUERY_KEYS)) {
    if (key === PROCESSING_FILTER_QUERY_KEYS.tab) continue;
    next.delete(key);
  }

  next.set(PROCESSING_FILTER_QUERY_KEYS.tab, PROCESSING_TAB_QUERY_VALUE);

  if (normalized.assetId) next.set(PROCESSING_FILTER_QUERY_KEYS.assetId, normalized.assetId);
  if (normalized.status) next.set(PROCESSING_FILTER_QUERY_KEYS.status, normalized.status);
  if (normalized.strategy) next.set(PROCESSING_FILTER_QUERY_KEYS.strategy, normalized.strategy);
  if (normalized.resolvedBy) next.set(PROCESSING_FILTER_QUERY_KEYS.resolvedBy, normalized.resolvedBy);
  if (normalized.search) next.set(PROCESSING_FILTER_QUERY_KEYS.search, normalized.search);
  if (normalized.page !== defaults.page) {
    next.set(PROCESSING_FILTER_QUERY_KEYS.page, String(normalized.page));
  }
  if (normalized.hasWarnings === true) next.set(PROCESSING_FILTER_QUERY_KEYS.hasWarnings, 'true');
  if (normalized.hasWarnings === false) next.set(PROCESSING_FILTER_QUERY_KEYS.hasWarnings, 'false');
  if (normalized.hasFallback === true) next.set(PROCESSING_FILTER_QUERY_KEYS.hasFallback, 'true');
  if (normalized.hasFallback === false) next.set(PROCESSING_FILTER_QUERY_KEYS.hasFallback, 'false');

  return next;
}

export function clearProcessingFilterParams(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of Object.values(PROCESSING_FILTER_QUERY_KEYS)) {
    next.delete(key);
  }
  return next;
}

export function processingFiltersToApiQuery(filters: ProcessingUrlFilters): {
  status?: string;
  strategy?: string;
  resolved_by?: string;
  search?: string;
  page: number;
  page_size: number;
  has_warnings?: boolean;
  has_fallback?: boolean;
} {
  const normalized = normalizeProcessingFilters(filters);
  return {
    status: normalized.status || undefined,
    strategy: normalized.strategy || undefined,
    resolved_by: normalized.resolvedBy || undefined,
    search: normalized.search || undefined,
    page: normalized.page,
    page_size: DEFAULT_LIST_PAGE_SIZE,
    has_warnings: normalized.hasWarnings ?? undefined,
    has_fallback: normalized.hasFallback ?? undefined,
  };
}

export function mergeProcessingFilterPatch(
  current: ProcessingUrlFilters,
  patch: Partial<ProcessingUrlFilters>,
  options?: { resetPage?: boolean }
): ProcessingUrlFilters {
  let next = normalizeProcessingFilters({ ...current, ...patch });
  const filterChanged =
    patch.status != null ||
    patch.strategy != null ||
    patch.resolvedBy != null ||
    patch.search != null ||
    patch.hasWarnings != null ||
    patch.hasFallback != null;
  if (options?.resetPage || filterChanged) {
    next = { ...next, page: 1 };
  }
  return next;
}

export const PROCESSING_PAGE_SIZE_OPTIONS = TABLE_PAGE_SIZE_OPTIONS;
