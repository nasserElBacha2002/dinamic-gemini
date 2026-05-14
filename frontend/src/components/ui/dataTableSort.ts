import type { DataTableColumn, DataTableSortDirection, DataTableSortType } from './DataTable';

function isEmpty(value: unknown): boolean {
  return value == null || value === '';
}

function toTime(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === 'number' && !Number.isNaN(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const t = Date.parse(value);
    return Number.isNaN(t) ? NaN : t;
  }
  return NaN;
}

function compareBySortType(a: unknown, b: unknown, sortType: DataTableSortType): number {
  switch (sortType) {
    case 'number': {
      const na = typeof a === 'number' ? a : Number(a);
      const nb = typeof b === 'number' ? b : Number(b);
      if (Number.isNaN(na) && Number.isNaN(nb)) return 0;
      if (Number.isNaN(na)) return 1;
      if (Number.isNaN(nb)) return -1;
      return na - nb;
    }
    case 'boolean': {
      return Number(Boolean(a)) - Number(Boolean(b));
    }
    case 'date': {
      const ta = toTime(a);
      const tb = toTime(b);
      if (Number.isNaN(ta) && Number.isNaN(tb)) return 0;
      if (Number.isNaN(ta)) return 1;
      if (Number.isNaN(tb)) return -1;
      return ta - tb;
    }
    case 'string':
    default:
      return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
  }
}

/**
 * Compare with empty/null/undefined last for both ascending and descending
 * (direction only applies when both values are non-empty).
 */
function compareWithEmptyLast(
  a: unknown,
  b: unknown,
  sortType: DataTableSortType,
  direction: 1 | -1
): number {
  const aE = isEmpty(a);
  const bE = isEmpty(b);
  if (aE && bE) return 0;
  if (aE) return 1;
  if (bE) return -1;
  return compareBySortType(a, b, sortType) * direction;
}

/**
 * Client-side sort for bounded/local row sets. Does not mutate `rows`.
 *
 * - Uses `sortComparator` when present, else `sortAccessor` + `sortType` (default `"string"`).
 * - Unknown `sortBy` or column without comparator/accessor: returns a shallow copy, original order.
 * - Stable tie-break: original row index.
 */
export function sortDataTableRows<T>(
  rows: readonly T[],
  columns: readonly DataTableColumn<T>[],
  sortBy: string,
  sortDir: DataTableSortDirection
): T[] {
  if (!sortBy) {
    return [...rows];
  }
  const col = columns.find((c) => c.id === sortBy);
  if (!col) {
    return [...rows];
  }

  const direction: 1 | -1 = sortDir === 'asc' ? 1 : -1;
  const indexed = rows.map((row, index) => ({ row, index }));

  if (col.sortComparator) {
    indexed.sort((ia, ib) => {
      const c = col.sortComparator!(ia.row, ib.row) * direction;
      if (c !== 0) return c;
      return ia.index - ib.index;
    });
    return indexed.map((x) => x.row);
  }

  if (!col.sortAccessor) {
    return [...rows];
  }

  const sortType: DataTableSortType = col.sortType ?? 'string';
  const accessor = col.sortAccessor;

  indexed.sort((ia, ib) => {
    const va = accessor(ia.row);
    const vb = accessor(ib.row);
    const c = compareWithEmptyLast(va, vb, sortType, direction);
    if (c !== 0) return c;
    return ia.index - ib.index;
  });
  return indexed.map((x) => x.row);
}
