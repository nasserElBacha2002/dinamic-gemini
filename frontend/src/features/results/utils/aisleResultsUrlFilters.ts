/**
 * URL filter contract for aisle results / conteo (`AislePositionsPage`).
 * Query string is the source of truth for navigable UI filters (client-side).
 * Preserves `jobId` and unknown params; omits defaults from the URL.
 */

import {
  DEFAULT_LIST_PAGE_SIZE,
  TABLE_PAGE_SIZE_OPTIONS,
} from '../../../constants/dataTable';
import type { DataTableSortDirection } from '../../../components/ui/DataTable';
import type { ResultsFilterKind } from '../selectors/resultsFilters';

export function aisleResultsSearchParamsEqual(a: URLSearchParams, b: URLSearchParams): boolean {
  const entriesA = [...a.entries()].sort(([ka], [kb]) => ka.localeCompare(kb));
  const entriesB = [...b.entries()].sort(([ka], [kb]) => ka.localeCompare(kb));
  if (entriesA.length !== entriesB.length) return false;
  return entriesA.every(([key, value], index) => {
    const [otherKey, otherValue] = entriesB[index] ?? [];
    return key === otherKey && value === otherValue;
  });
}

export const AISLE_RESULTS_FILTER_QUERY_KEYS = {
  filter: 'filter',
  q: 'q',
  page: 'page',
  pageSize: 'pageSize',
  tableSort: 'tableSort',
  sortBy: 'sortBy',
  sortDir: 'sortDir',
} as const;

/** Managed by job-run canonization separately; preserved when writing filters. */
export const AISLE_RESULTS_JOB_ID_QUERY_KEY = 'jobId';

export type AisleResultsTableSortMode = 'photo' | 'priority';

export const AISLE_RESULTS_SORT_COLUMNS = [
  'priority',
  'sku',
  'position_code',
  'qty',
  'review_status',
  'traceability',
  'confidence',
  'evidence',
  'updated',
] as const;

export type AisleResultsSortColumn = (typeof AISLE_RESULTS_SORT_COLUMNS)[number];

export type AisleResultsUrlFilters = {
  filter: ResultsFilterKind;
  q: string;
  page: number;
  pageSize: number;
  tableSort: AisleResultsTableSortMode;
  sortBy: AisleResultsSortColumn | null;
  sortDir: DataTableSortDirection;
};

const VALID_FILTERS: readonly ResultsFilterKind[] = [
  'all',
  'needs_review',
  'low_confidence',
  'qty_zero',
  'invalid_traceability',
  'missing_evidence',
] as const;

const VALID_TABLE_SORT: readonly AisleResultsTableSortMode[] = ['photo', 'priority'] as const;
const VALID_SORT_DIR: readonly DataTableSortDirection[] = ['asc', 'desc'] as const;
const PAGE_SIZE_SET = new Set<number>(TABLE_PAGE_SIZE_OPTIONS);
const SORT_COLUMN_SET = new Set<string>(AISLE_RESULTS_SORT_COLUMNS);
const FILTER_SET = new Set<string>(VALID_FILTERS);

export function createDefaultAisleResultsFilters(): AisleResultsUrlFilters {
  return {
    filter: 'all',
    q: '',
    page: 1,
    pageSize: DEFAULT_LIST_PAGE_SIZE,
    tableSort: 'photo',
    sortBy: null,
    sortDir: 'asc',
  };
}

function trimParam(value: string | null): string {
  return (value ?? '').trim();
}

function parsePositiveInt(value: string | null, fallback: number): number {
  const raw = trimParam(value);
  if (!raw) return fallback;
  if (!/^\d+$/.test(raw)) return fallback;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return fallback;
  return n;
}

function parsePageSize(value: string | null, fallback: number): number {
  const n = parsePositiveInt(value, fallback);
  return PAGE_SIZE_SET.has(n) ? n : fallback;
}

function parseFilter(value: string | null, fallback: ResultsFilterKind): ResultsFilterKind {
  const raw = trimParam(value);
  if (!raw || !FILTER_SET.has(raw)) return fallback;
  return raw as ResultsFilterKind;
}

function parseTableSort(
  value: string | null,
  fallback: AisleResultsTableSortMode
): AisleResultsTableSortMode {
  const raw = trimParam(value);
  if (!raw || !(VALID_TABLE_SORT as readonly string[]).includes(raw)) return fallback;
  return raw as AisleResultsTableSortMode;
}

function parseSortBy(value: string | null): AisleResultsSortColumn | null {
  const raw = trimParam(value);
  if (!raw || !SORT_COLUMN_SET.has(raw)) return null;
  return raw as AisleResultsSortColumn;
}

function parseSortDir(
  value: string | null,
  fallback: DataTableSortDirection
): DataTableSortDirection {
  const raw = trimParam(value).toLowerCase();
  if (!(VALID_SORT_DIR as readonly string[]).includes(raw)) return fallback;
  return raw as DataTableSortDirection;
}

export function normalizeAisleResultsFilters(
  filters: AisleResultsUrlFilters
): AisleResultsUrlFilters {
  const defaults = createDefaultAisleResultsFilters();
  const q = filters.q.trim();
  const page = Number.isFinite(filters.page) && filters.page >= 1 ? Math.floor(filters.page) : 1;
  const pageSize = PAGE_SIZE_SET.has(filters.pageSize) ? filters.pageSize : defaults.pageSize;
  const filter = FILTER_SET.has(filters.filter) ? filters.filter : defaults.filter;
  const tableSort = (VALID_TABLE_SORT as readonly string[]).includes(filters.tableSort)
    ? filters.tableSort
    : defaults.tableSort;
  const sortBy =
    filters.sortBy != null && SORT_COLUMN_SET.has(filters.sortBy) ? filters.sortBy : null;
  const sortDir =
    sortBy == null
      ? defaults.sortDir
      : (VALID_SORT_DIR as readonly string[]).includes(filters.sortDir)
        ? filters.sortDir
        : defaults.sortDir;
  return { filter, q, page, pageSize, tableSort, sortBy, sortDir };
}

export function isAisleResultsSortColumn(value: string): value is AisleResultsSortColumn {
  return SORT_COLUMN_SET.has(value);
}

export function parseAisleResultsFilters(
  params: URLSearchParams,
  defaults: AisleResultsUrlFilters = createDefaultAisleResultsFilters()
): AisleResultsUrlFilters {
  return normalizeAisleResultsFilters({
    filter: parseFilter(params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.filter), defaults.filter),
    q: trimParam(params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.q)),
    page: parsePositiveInt(params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.page), defaults.page),
    pageSize: parsePageSize(
      params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.pageSize),
      defaults.pageSize
    ),
    tableSort: parseTableSort(
      params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.tableSort),
      defaults.tableSort
    ),
    sortBy: parseSortBy(params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.sortBy)),
    sortDir: parseSortDir(
      params.get(AISLE_RESULTS_FILTER_QUERY_KEYS.sortDir),
      defaults.sortDir
    ),
  });
}

export function areAisleResultsFiltersEqual(
  a: AisleResultsUrlFilters,
  b: AisleResultsUrlFilters
): boolean {
  const na = normalizeAisleResultsFilters(a);
  const nb = normalizeAisleResultsFilters(b);
  return (
    na.filter === nb.filter &&
    na.q === nb.q &&
    na.page === nb.page &&
    na.pageSize === nb.pageSize &&
    na.tableSort === nb.tableSort &&
    na.sortBy === nb.sortBy &&
    na.sortDir === nb.sortDir
  );
}

export function writeAisleResultsFilters(
  params: URLSearchParams,
  filters: AisleResultsUrlFilters,
  defaults: AisleResultsUrlFilters = createDefaultAisleResultsFilters()
): URLSearchParams {
  const next = new URLSearchParams(params);
  const normalized = normalizeAisleResultsFilters(filters);

  for (const key of Object.values(AISLE_RESULTS_FILTER_QUERY_KEYS)) {
    next.delete(key);
  }

  if (normalized.filter !== defaults.filter) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.filter, normalized.filter);
  }
  if (normalized.q) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.q, normalized.q);
  }
  if (normalized.page !== defaults.page) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.page, String(normalized.page));
  }
  if (normalized.pageSize !== defaults.pageSize) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.pageSize, String(normalized.pageSize));
  }
  if (normalized.tableSort !== defaults.tableSort) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.tableSort, normalized.tableSort);
  }
  if (normalized.sortBy != null) {
    next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.sortBy, normalized.sortBy);
    if (normalized.sortDir !== defaults.sortDir) {
      next.set(AISLE_RESULTS_FILTER_QUERY_KEYS.sortDir, normalized.sortDir);
    }
  }

  return next;
}

export type AisleResultsFilterUpdateOptions = {
  resetPage?: boolean;
  /** When true, clamp page into 1..maxPage after merge (for out-of-range URLs). */
  clampPageTo?: number;
};

export function mergeAisleResultsFilterPatch(
  current: AisleResultsUrlFilters,
  patch: Partial<AisleResultsUrlFilters>,
  options?: AisleResultsFilterUpdateOptions
): AisleResultsUrlFilters {
  let next = normalizeAisleResultsFilters({ ...current, ...patch });
  if (options?.resetPage) {
    next = { ...next, page: 1 };
  }
  const maxPage = options?.clampPageTo;
  if (typeof maxPage === 'number' && Number.isFinite(maxPage) && maxPage >= 1) {
    const clamped = Math.min(Math.max(1, next.page), Math.floor(maxPage));
    next = { ...next, page: clamped };
  }
  return next;
}
