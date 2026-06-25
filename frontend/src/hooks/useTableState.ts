import { useCallback, useMemo, useState } from 'react';
import type { DataTableSortDirection } from '../components/ui/DataTable';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';

const EMPTY_FILTERS: Record<string, unknown> = {};

export interface UseTableStateOptions<
  TFilters extends Record<string, unknown> = Record<string, unknown>,
> {
  initialPage?: number;
  initialPageSize?: number;
  initialSortBy?: string;
  initialSortDir?: DataTableSortDirection;
  initialFilters?: TFilters;
}

export interface UseTableStateReturn<
  TFilters extends Record<string, unknown> = Record<string, unknown>,
> {
  page: number;
  pageSize: number;
  sortBy: string;
  sortDir: DataTableSortDirection;
  filters: TFilters;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  setSort: (sortBy: string, sortDir: DataTableSortDirection) => void;
  /** Updates sort without resetting page (e.g. hybrid client-side column sort). */
  setSortWithoutPageReset: (sortBy: string, sortDir: DataTableSortDirection) => void;
  setFilter: <K extends keyof TFilters>(key: K, value: TFilters[K]) => void;
  resetFilters: () => void;
  resetTableState: () => void;
}

/**
 * Shared pagination, sort, and filter state for operational tables.
 * Works with both server-driven and client-side table pipelines.
 */
export function useTableState<
  TFilters extends Record<string, unknown> = Record<string, unknown>,
>(options: UseTableStateOptions<TFilters> = {}): UseTableStateReturn<TFilters> {
  const {
    initialPage = 1,
    initialPageSize = DEFAULT_LIST_PAGE_SIZE,
    initialSortBy = '',
    initialSortDir = 'asc',
    initialFilters,
  } = options;

  const resolvedInitialFilters = useMemo(
    () => (initialFilters ?? EMPTY_FILTERS) as TFilters,
    [initialFilters]
  );

  const [page, setPageState] = useState(initialPage);
  const [pageSize, setPageSizeState] = useState(initialPageSize);
  const [sortBy, setSortBy] = useState(initialSortBy);
  const [sortDir, setSortDir] = useState<DataTableSortDirection>(initialSortDir);
  const [filters, setFilters] = useState<TFilters>(resolvedInitialFilters);

  const setPage = useCallback((next: number) => {
    setPageState(next);
  }, []);

  const setPageSize = useCallback((next: number) => {
    setPageSizeState(next);
    setPageState(1);
  }, []);

  const setSort = useCallback((nextSortBy: string, nextSortDir: DataTableSortDirection) => {
    setSortBy(nextSortBy);
    setSortDir(nextSortDir);
    setPageState(1);
  }, []);

  const setSortWithoutPageReset = useCallback((nextSortBy: string, nextSortDir: DataTableSortDirection) => {
    setSortBy(nextSortBy);
    setSortDir(nextSortDir);
  }, []);

  const setFilter = useCallback(<K extends keyof TFilters>(key: K, value: TFilters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPageState(1);
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(resolvedInitialFilters);
    setPageState(1);
  }, [resolvedInitialFilters]);

  const resetTableState = useCallback(() => {
    setPageState(initialPage);
    setPageSizeState(initialPageSize);
    setSortBy(initialSortBy);
    setSortDir(initialSortDir);
    setFilters(resolvedInitialFilters);
  }, [initialPage, initialPageSize, initialSortBy, initialSortDir, resolvedInitialFilters]);

  return {
    page,
    pageSize,
    sortBy,
    sortDir,
    filters,
    setPage,
    setPageSize,
    setSort,
    setSortWithoutPageReset,
    setFilter,
    resetFilters,
    resetTableState,
  };
}
