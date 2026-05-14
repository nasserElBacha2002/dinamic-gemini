import { describe, expect, it } from 'vitest';
import type { DataTableColumn } from '../src/components/ui/DataTable';
import { sortDataTableRows } from '../src/components/ui/dataTableSort';

type Row = { id: string; name: string; n?: number | null; d?: string | null; b?: boolean };

function cols(): DataTableColumn<Row>[] {
  return [
    { id: 'name', label: 'Name', cell: (r) => r.name, sortable: true, sortType: 'string', sortAccessor: (r) => r.name },
    { id: 'n', label: 'N', cell: (r) => String(r.n), sortable: true, sortType: 'number', sortAccessor: (r) => r.n },
    { id: 'd', label: 'D', cell: () => '', sortable: true, sortType: 'date', sortAccessor: (r) => r.d },
    { id: 'b', label: 'B', cell: () => '', sortable: true, sortType: 'boolean', sortAccessor: (r) => r.b },
  ];
}

describe('sortDataTableRows', () => {
  it('returns a copy in original order when sortBy is empty', () => {
    const rows: Row[] = [
      { id: '1', name: 'b' },
      { id: '2', name: 'a' },
    ];
    const out = sortDataTableRows(rows, cols(), '', 'asc');
    expect(out.map((r) => r.id)).toEqual(['1', '2']);
    expect(out).not.toBe(rows);
  });

  it('sorts strings ascending and descending', () => {
    const rows: Row[] = [
      { id: '1', name: 'b' },
      { id: '2', name: 'a' },
      { id: '3', name: 'c' },
    ];
    expect(sortDataTableRows(rows, cols(), 'name', 'asc').map((r) => r.name)).toEqual(['a', 'b', 'c']);
    expect(sortDataTableRows(rows, cols(), 'name', 'desc').map((r) => r.name)).toEqual(['c', 'b', 'a']);
  });

  it('sorts numbers ascending and descending', () => {
    const rows: Row[] = [
      { id: '1', name: 'x', n: 10 },
      { id: '2', name: 'x', n: 2 },
      { id: '3', name: 'x', n: 7 },
    ];
    expect(sortDataTableRows(rows, cols(), 'n', 'asc').map((r) => r.n)).toEqual([2, 7, 10]);
    expect(sortDataTableRows(rows, cols(), 'n', 'desc').map((r) => r.n)).toEqual([10, 7, 2]);
  });

  it('sorts dates by ISO ascending and descending', () => {
    const rows: Row[] = [
      { id: '1', name: 'x', d: '2024-01-02T00:00:00.000Z' },
      { id: '2', name: 'x', d: '2024-01-01T00:00:00.000Z' },
      { id: '3', name: 'x', d: '2024-01-03T00:00:00.000Z' },
    ];
    expect(sortDataTableRows(rows, cols(), 'd', 'asc').map((r) => r.d)).toEqual([
      '2024-01-01T00:00:00.000Z',
      '2024-01-02T00:00:00.000Z',
      '2024-01-03T00:00:00.000Z',
    ]);
    expect(sortDataTableRows(rows, cols(), 'd', 'desc').map((r) => r.d)).toEqual([
      '2024-01-03T00:00:00.000Z',
      '2024-01-02T00:00:00.000Z',
      '2024-01-01T00:00:00.000Z',
    ]);
  });

  it('sorts booleans', () => {
    const rows: Row[] = [
      { id: '1', name: 'x', b: true },
      { id: '2', name: 'x', b: false },
    ];
    const asc = sortDataTableRows(rows, cols(), 'b', 'asc');
    expect(asc.map((r) => r.b)).toEqual([false, true]);
  });

  it('places null/undefined last for asc and desc (non-empty first)', () => {
    const c: DataTableColumn<Row>[] = [
      { id: 'n', label: 'N', cell: () => '', sortType: 'number', sortAccessor: (r) => r.n },
    ];
    const rows: Row[] = [
      { id: '1', name: 'a', n: 1 },
      { id: '2', name: 'b', n: null },
      { id: '3', name: 'c', n: 0 },
    ];
    const ascIds = sortDataTableRows(rows, c, 'n', 'asc').map((r) => r.id);
    expect(ascIds[ascIds.length - 1]).toBe('2');
    const descIds = sortDataTableRows(rows, c, 'n', 'desc').map((r) => r.id);
    expect(descIds[descIds.length - 1]).toBe('2');
  });

  it('preserves stable order for equal values (tie-break by index)', () => {
    const rows: Row[] = [
      { id: 'z', name: 'same' },
      { id: 'y', name: 'same' },
      { id: 'x', name: 'same' },
    ];
    const out = sortDataTableRows(rows, cols(), 'name', 'asc');
    expect(out.map((r) => r.id)).toEqual(['z', 'y', 'x']);
  });

  it('uses custom sortComparator when provided', () => {
    const c: DataTableColumn<Row>[] = [
      {
        id: 'x',
        label: 'X',
        cell: () => '',
        sortComparator: (a, b) => a.id.localeCompare(b.id),
      },
    ];
    const rows: Row[] = [
      { id: 'b', name: 'q' },
      { id: 'a', name: 'q' },
    ];
    expect(sortDataTableRows(rows, c, 'x', 'asc').map((r) => r.id)).toEqual(['a', 'b']);
    expect(sortDataTableRows(rows, c, 'x', 'desc').map((r) => r.id)).toEqual(['b', 'a']);
  });

  it('uses custom sortAccessor', () => {
    const c: DataTableColumn<Row>[] = [
      {
        id: 'rev',
        label: 'R',
        cell: () => '',
        sortType: 'string',
        sortAccessor: (r) => r.name.split('').reverse().join(''),
      },
    ];
    const rows: Row[] = [
      { id: '1', name: 'ab' },
      { id: '2', name: 'ba' },
    ];
    const asc = sortDataTableRows(rows, c, 'rev', 'asc');
    expect(asc.map((r) => r.name)).toEqual(['ba', 'ab']);
  });

  it('returns original order for unknown sortBy', () => {
    const rows: Row[] = [
      { id: '1', name: 'b' },
      { id: '2', name: 'a' },
    ];
    const out = sortDataTableRows(rows, cols(), 'missing', 'asc');
    expect(out.map((r) => r.id)).toEqual(['1', '2']);
  });

  it('returns original order when column has no accessor or comparator', () => {
    const c: DataTableColumn<Row>[] = [{ id: 'only', label: 'O', cell: (r) => r.name, sortable: true }];
    const rows: Row[] = [
      { id: '1', name: 'b' },
      { id: '2', name: 'a' },
    ];
    const out = sortDataTableRows(rows, c, 'only', 'asc');
    expect(out.map((r) => r.id)).toEqual(['1', '2']);
  });

  it('does not mutate the input rows array', () => {
    const rows: Row[] = [{ id: '1', name: 'b' }];
    const frozen = rows.slice();
    sortDataTableRows(rows, cols(), 'name', 'asc');
    expect(rows).toEqual(frozen);
  });
});
