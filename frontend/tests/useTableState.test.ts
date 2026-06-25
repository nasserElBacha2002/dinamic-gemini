import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTableState } from '../src/hooks/useTableState';
import { DEFAULT_LIST_PAGE_SIZE } from '../src/constants/dataTable';

describe('useTableState', () => {
  it('initializes with defaults', () => {
    const { result } = renderHook(() => useTableState());
    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(DEFAULT_LIST_PAGE_SIZE);
    expect(result.current.sortBy).toBe('');
    expect(result.current.sortDir).toBe('asc');
    expect(result.current.filters).toEqual({});
  });

  it('initializes with custom values', () => {
    const { result } = renderHook(() =>
      useTableState({
        initialPage: 2,
        initialPageSize: 50,
        initialSortBy: 'created_at',
        initialSortDir: 'desc',
        initialFilters: { status: 'active' },
      })
    );
    expect(result.current.page).toBe(2);
    expect(result.current.pageSize).toBe(50);
    expect(result.current.sortBy).toBe('created_at');
    expect(result.current.sortDir).toBe('desc');
    expect(result.current.filters).toEqual({ status: 'active' });
  });

  it('resets page to 1 when page size changes', () => {
    const { result } = renderHook(() =>
      useTableState({ initialPage: 3, initialPageSize: 25 })
    );
    act(() => {
      result.current.setPageSize(50);
    });
    expect(result.current.pageSize).toBe(50);
    expect(result.current.page).toBe(1);
  });

  it('resets page to 1 when sort changes', () => {
    const { result } = renderHook(() => useTableState({ initialPage: 4 }));
    act(() => {
      result.current.setSort('name', 'desc');
    });
    expect(result.current.sortBy).toBe('name');
    expect(result.current.sortDir).toBe('desc');
    expect(result.current.page).toBe(1);
  });

  it('resets page to 1 when a filter changes', () => {
    const { result } = renderHook(() =>
      useTableState<{ q: string }>({ initialPage: 2, initialFilters: { q: '' } })
    );
    act(() => {
      result.current.setFilter('q', 'abc');
    });
    expect(result.current.filters.q).toBe('abc');
    expect(result.current.page).toBe(1);
  });

  it('resetFilters restores initial filters and page', () => {
    const initialFilters = { q: '' };
    const { result } = renderHook(() =>
      useTableState<{ q: string }>({ initialPage: 1, initialFilters })
    );
    act(() => {
      result.current.setFilter('q', 'search');
      result.current.setPage(3);
    });
    act(() => {
      result.current.resetFilters();
    });
    expect(result.current.filters).toEqual({ q: '' });
    expect(result.current.page).toBe(1);
  });

  it('resetTableState restores all initial values', () => {
    const { result } = renderHook(() =>
      useTableState({
        initialPage: 1,
        initialPageSize: 25,
        initialSortBy: 'created_at',
        initialSortDir: 'desc',
        initialFilters: { status: 'draft' },
      })
    );
    act(() => {
      result.current.setPage(5);
      result.current.setPageSize(100);
      result.current.setSort('name', 'asc');
      result.current.setFilter('status', 'active');
    });
    act(() => {
      result.current.resetTableState();
    });
    expect(result.current.page).toBe(1);
    expect(result.current.pageSize).toBe(25);
    expect(result.current.sortBy).toBe('created_at');
    expect(result.current.sortDir).toBe('desc');
    expect(result.current.filters).toEqual({ status: 'draft' });
  });

  it('setSortState updates sort without resetting page', () => {
    const { result } = renderHook(() => useTableState({ initialPage: 3 }));
    act(() => {
      result.current.setSortState('name', 'desc');
    });
    expect(result.current.sortBy).toBe('name');
    expect(result.current.sortDir).toBe('desc');
    expect(result.current.page).toBe(3);
  });

  it('uses a stable empty filters object when initialFilters is omitted', () => {
    const { result, rerender } = renderHook(() => useTableState<{ q: string }>());
    const firstReset = result.current.resetFilters;
    rerender();
    expect(result.current.resetFilters).toBe(firstReset);
    act(() => {
      result.current.setFilter('q', 'x');
    });
    act(() => {
      result.current.resetFilters();
    });
    expect(result.current.filters).toEqual({});
  });
});
