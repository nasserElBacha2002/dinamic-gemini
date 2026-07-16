/**
 * DataTable — Sprint 2.4 operational table shell (Re diseño 3.3 §8.6, §10) + mobile cards.
 *
 * - **Server-driven sort/pagination:** parent owns query state and passes `sort` / `pagination`; this component
 *   only renders controls and fires callbacks (no hidden client-side sort of `rows`).
 * - **Page size changes:** when the user picks a new rows-per-page value, this component calls
 *   `onPageSizeChange(newSize)` (if provided) and **always** `onPageChange(1)` so the current page does not
 *   point past the last page. Callers should not rely on duplicating that reset (idempotent if they do).
 * - **Empty rows:** if `emptyState` is omitted and the table is not loading, a **default** empty message is shown
 *   so the region is never a silent blank shell.
 * - **Density:** defaults to `size="small"` and sticky header for scan-heavy operational lists.
 * - **Mobile:** when `renderMobileItem` is provided and viewport is compact (`!md`), rows render as cards
 *   using the **same** `rows` / loading / empty / pagination — no duplicate data fetching.
 * - **Composition:** wrap with `SectionCard`, place `FilterToolbar` above, use `RowActionMenu` / `StatusBadge` in `cell`.
 *
 * **Status in cells:** prefer `StatusBadge` when domain maps to redesign semantics; use `StatusChip` when the row
 * already uses mapper output (e.g. review status color helpers) until a single semantic mapping exists.
 *
 * **Limitations:** No built-in row selection or column resize; add per screen when contracts require them.
 *
 * **Sort metadata (optional):** `sortType`, `sortAccessor`, `sortComparator`, `serverSortKey` on columns are
 * for parents and helpers such as `sortDataTableRows` — this component does not reorder `rows` itself.
 */

import type { MouseEvent, ReactNode } from 'react';
import {
  Box,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableFooter,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY, TABLE_PAGE_SIZE_OPTIONS } from '../../constants/dataTable';
import { useAppBreakpoint } from '../../hooks/useAppBreakpoint';
import EmptyState from './EmptyState';

export type DataTableSortDirection = 'asc' | 'desc';

export type DataTableSortType = 'string' | 'number' | 'date' | 'boolean';

export interface DataTableColumn<T> {
  /** Stable id; for `sortable` columns this is often sent as API `sort_by` when parent wires it that way. */
  id: string;
  label: string;
  align?: 'left' | 'right' | 'center';
  sortable?: boolean;
  /** Used by client-side helpers (e.g. `sortDataTableRows`); not applied inside `DataTable`. */
  sortType?: DataTableSortType;
  /** Raw value for comparisons — never use translated labels or rendered nodes. */
  sortAccessor?: (row: T) => unknown;
  /** Full row comparison when column order cannot be expressed as a scalar accessor. */
  sortComparator?: (a: T, b: T) => number;
  /** When API `sort_by` must differ from `id` (server-driven tables). */
  serverSortKey?: string;
  width?: number | string;
  /** Cell content for one row. */
  cell: (row: T) => ReactNode;
}

export interface DataTableSortModel {
  sortBy: string;
  sortDir: DataTableSortDirection;
  onSortChange: (sortBy: string, sortDir: DataTableSortDirection) => void;
}

export interface DataTablePaginationModel {
  /** 1-based page index (matches v3 list APIs). */
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  /**
   * When the user changes rows per page, `DataTable` calls this and then **`onPageChange(1)`** (see file doc).
   * Optional only for read-only pagination display (unusual); typical callers always provide it.
   */
  onPageSizeChange?: (pageSize: number) => void;
}

export interface DataTableProps<T> {
  rows: readonly T[];
  rowKey: (row: T) => string;
  columns: readonly DataTableColumn<T>[];
  /** When true, header + skeleton body (operational loading; not a page-level spinner). */
  loading?: boolean;
  skeletonRows?: number;
  /**
   * Shown when `!loading && rows.length === 0`. If omitted, a built-in minimal message is used
   * (`DATATABLE_DEFAULT_EMPTY_MESSAGE` from `constants/dataTable`).
   */
  emptyState?: { title?: string; message: string; action?: ReactNode };
  sort?: DataTableSortModel;
  pagination?: DataTablePaginationModel;
  size?: 'small' | 'medium';
  stickyHeader?: boolean;
  /** Row hover affordance (§10 row hover). */
  rowHover?: boolean;
  /** Optional row tap target (e.g. navigate); use stopPropagation on nested interactive cells to avoid double handling. */
  onRowClick?: (row: T) => void;
  /** Applied to the underlying `<Table>` for stable test selectors. */
  testId?: string;
  /**
   * Compact viewport card renderer. Same `rows` / pagination / loading as the desktop table.
   * When omitted, compact viewports keep the horizontal-scrolling table.
   */
  renderMobileItem?: (row: T) => ReactNode;
  /**
   * When true (default), show a small “scroll for more columns” hint above the table on compact
   * viewports when there is no `renderMobileItem`.
   */
  showHorizontalScrollHint?: boolean;
}

function resolveClickElement(target: EventTarget | null): Element | null {
  if (target instanceof Element) return target;
  if (target instanceof Text) return target.parentElement;
  return null;
}

/** Clicks on nested controls must not trigger row-level navigation (e.g. action menus, links). */
function clickTargetShouldSkipRowNavigation(target: EventTarget | null): boolean {
  const el = resolveClickElement(target);
  if (!el) return false;
  return Boolean(
    el.closest(
      [
        'button',
        'a[href]',
        'input',
        'textarea',
        'select',
        '[role="button"]',
        '[role="menuitem"]',
        '[role="menu"]',
        'label',
        '[data-datatable-skip-row-click]',
      ].join(', ')
    )
  );
}

function SkeletonBody({ columns, rows }: { columns: number; rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, ri) => (
        <TableRow key={`sk-${ri}`}>
          {Array.from({ length: columns }).map((__, ci) => (
            <TableCell key={ci} size="small" padding="normal">
              <Skeleton variant="text" width={ci === 0 ? '70%' : '55%'} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

function PaginationBar({ pagination }: { pagination: DataTablePaginationModel }) {
  const { t } = useTranslation();
  return (
    <Box sx={{ overflowX: 'auto', width: '100%', minWidth: 0 }}>
      <TablePagination
        component="div"
        count={pagination.totalItems}
        page={Math.max(0, pagination.page - 1)}
        onPageChange={(_, nextZeroBased) => {
          pagination.onPageChange(nextZeroBased + 1);
        }}
        rowsPerPage={pagination.pageSize}
        onRowsPerPageChange={(e) => {
          const next = Number(e.target.value);
          if (next === pagination.pageSize) return;
          pagination.onPageSizeChange?.(next);
          pagination.onPageChange(1);
        }}
        rowsPerPageOptions={[...TABLE_PAGE_SIZE_OPTIONS]}
        labelRowsPerPage={t('common.rows_per_page')}
      />
    </Box>
  );
}

export default function DataTable<T>({
  rows,
  rowKey,
  columns,
  loading = false,
  skeletonRows = 6,
  emptyState,
  sort,
  pagination,
  size = 'small',
  stickyHeader = true,
  rowHover = true,
  onRowClick,
  testId,
  renderMobileItem,
  showHorizontalScrollHint = true,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const { isCompact } = useAppBreakpoint();
  const useMobileCards = Boolean(renderMobileItem) && isCompact;
  const colCount = columns.length;
  const emptyDisplay =
    !loading && rows.length === 0
      ? (emptyState ?? { message: t(DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY) })
      : null;
  const showEmpty = Boolean(emptyDisplay);

  if (useMobileCards) {
    return (
      <Box
        data-testid={testId}
        sx={{ width: '100%', maxWidth: '100%', minWidth: 0 }}
        aria-busy={loading}
      >
        {loading ? (
          <Stack spacing={1.5}>
            {Array.from({ length: skeletonRows }).map((_, i) => (
              <Skeleton key={`msk-${i}`} variant="rounded" height={96} />
            ))}
          </Stack>
        ) : showEmpty && emptyDisplay ? (
          <Paper variant="outlined" sx={{ borderRadius: 1 }}>
            <Box sx={{ p: 2 }}>
              <EmptyState
                title={emptyDisplay.title}
                message={emptyDisplay.message}
                action={emptyDisplay.action}
                padding={3}
              />
            </Box>
          </Paper>
        ) : (
          <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
            {rows.map((row) => (
              <Box component="li" key={rowKey(row)} sx={{ minWidth: 0 }}>
                {renderMobileItem!(row)}
              </Box>
            ))}
          </Stack>
        )}
        {pagination && !showEmpty && !loading ? (
          <Paper variant="outlined" sx={{ mt: 1.5, borderRadius: 1 }}>
            <PaginationBar pagination={pagination} />
          </Paper>
        ) : null}
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
      {showHorizontalScrollHint && isCompact && !loading && !showEmpty ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
          {t('table.scroll_hint')}
        </Typography>
      ) : null}
      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{
          borderRadius: 1,
          width: '100%',
          maxWidth: '100%',
          minWidth: 0,
          overflowX: 'auto',
        }}
      >
        <Table size={size} stickyHeader={stickyHeader} aria-busy={loading} data-testid={testId}>
          <TableHead>
            <TableRow>
              {columns.map((col) => (
                <TableCell
                  key={col.id}
                  align={col.align ?? 'left'}
                  sx={col.width != null ? { width: col.width } : undefined}
                >
                  {col.sortable && sort ? (
                    <TableSortLabel
                      active={sort.sortBy === col.id}
                      direction={sort.sortBy === col.id ? sort.sortDir : 'asc'}
                      onClick={() => {
                        const active = sort.sortBy === col.id;
                        const nextDir: DataTableSortDirection =
                          active && sort.sortDir === 'asc' ? 'desc' : 'asc';
                        sort.onSortChange(col.id, nextDir);
                      }}
                    >
                      {col.label}
                    </TableSortLabel>
                  ) : (
                    col.label
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <SkeletonBody columns={colCount} rows={skeletonRows} />
            ) : showEmpty && emptyDisplay ? (
              <TableRow>
                <TableCell colSpan={colCount} sx={{ border: 0, p: 0, verticalAlign: 'top' }}>
                  <Box sx={{ p: 2 }}>
                    <EmptyState
                      title={emptyDisplay.title}
                      message={emptyDisplay.message}
                      action={emptyDisplay.action}
                      padding={3}
                    />
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  key={rowKey(row)}
                  hover={rowHover}
                  onClick={
                    onRowClick
                      ? (e: MouseEvent<HTMLTableRowElement>) => {
                          if (clickTargetShouldSkipRowNavigation(e.target)) return;
                          onRowClick(row);
                        }
                      : undefined
                  }
                  sx={onRowClick ? { cursor: 'pointer' } : undefined}
                >
                  {columns.map((col) => (
                    <TableCell key={col.id} align={col.align ?? 'left'} size={size}>
                      {col.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
          {pagination && !showEmpty && !loading ? (
            <TableFooter>
              <TableRow>
                <TableCell colSpan={colCount} sx={{ borderBottom: 'none', p: 0 }}>
                  <PaginationBar pagination={pagination} />
                </TableCell>
              </TableRow>
            </TableFooter>
          ) : null}
        </Table>
      </TableContainer>
    </Box>
  );
}
