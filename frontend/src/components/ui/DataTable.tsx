/**
 * DataTable — operational table shell with explicit mobile strategy.
 *
 * Every usage must declare `mobile`. Card structure is owned here; feature code declares
 * domain fields only. Horizontal scroll is an explicit exception with a reason.
 */

import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
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
import type { Breakpoint } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import { DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY, TABLE_PAGE_SIZE_OPTIONS } from '../../constants/dataTable';
import { useAppBreakpoint } from '../../hooks/useAppBreakpoint';
import EmptyState from './EmptyState';
import DataTableMobileCard from './DataTableMobileCard';
import type { RowActionMenuItem } from './RowActionMenu';

export type DataTableSortDirection = 'asc' | 'desc';
export type DataTableSortType = 'string' | 'number' | 'date' | 'boolean';

export type DataTableMobileMode = 'card' | 'horizontal-scroll' | 'key-value' | 'comparison' | 'log-view';

export interface DataTableMobileField<T> {
  id: string;
  label: ReactNode;
  value: (row: T) => ReactNode;
  hidden?: (row: T) => boolean;
  priority?: 'primary' | 'secondary';
  fullWidth?: boolean;
}

export interface DataTableMobileConfig<T> {
  mode: DataTableMobileMode;
  breakpoint?: Breakpoint;
  title?: (row: T) => ReactNode;
  subtitle?: (row: T) => ReactNode;
  status?: (row: T) => ReactNode;
  fields?: readonly DataTableMobileField<T>[];
  actions?: (row: T) => readonly RowActionMenuItem[];
  primaryAction?: (row: T) => ReactNode;
  ariaLabel?: (row: T) => string;
  showScrollHint?: boolean;
  stickyColumnId?: string;
  /** Required for horizontal-scroll / log-view exceptions. */
  reason?: string;
}

export interface DataTableColumn<T> {
  /** Stable id; for `sortable` columns this is often sent as API `sort_by` when parent wires it that way. */
  id: string;
  label: string;
  align?: 'left' | 'right' | 'center';
  sortable?: boolean;
  sortType?: DataTableSortType;
  sortAccessor?: (row: T) => unknown;
  sortComparator?: (a: T, b: T) => number;
  serverSortKey?: string;
  width?: number | string;
  cell: (row: T) => ReactNode;
}

export interface DataTableSortModel {
  sortBy: string;
  sortDir: DataTableSortDirection;
  onSortChange: (sortBy: string, sortDir: DataTableSortDirection) => void;
}

export interface DataTablePaginationModel {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
}

export interface DataTableProps<T> {
  rows: readonly T[];
  rowKey: (row: T) => string;
  columns: readonly DataTableColumn<T>[];
  mobile: DataTableMobileConfig<T>;
  loading?: boolean;
  skeletonRows?: number;
  emptyState?: { title?: string; message: string; action?: ReactNode };
  sort?: DataTableSortModel;
  pagination?: DataTablePaginationModel;
  size?: 'small' | 'medium';
  stickyHeader?: boolean;
  rowHover?: boolean;
  onRowClick?: (row: T) => void;
  testId?: string;
}

function resolveClickElement(target: EventTarget | null): Element | null {
  if (target instanceof Element) return target;
  if (target instanceof Text) return target.parentElement;
  return null;
}

/** Clicks on nested controls must not trigger row-level navigation. */
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
        onPageChange={(_, nextZeroBased) => pagination.onPageChange(nextZeroBased + 1)}
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

function useHorizontalOverflow<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const update = () => {
      setOverflowing(el.scrollWidth > el.clientWidth + 1);
    };

    update();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, overflowing };
}

function MobileCards<T>({
  rows,
  rowKey,
  mobile,
  onRowClick,
}: {
  rows: readonly T[];
  rowKey: (row: T) => string;
  mobile: DataTableMobileConfig<T>;
  onRowClick?: (row: T) => void;
}) {
  return (
    <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', m: 0, p: 0 }}>
      {rows.map((row) => {
        const fields = (mobile.fields ?? [])
          .filter((field) => !field.hidden?.(row))
          .map((field) => ({
            id: field.id,
            label: field.label,
            value: field.value(row),
            priority: field.priority,
            fullWidth: field.fullWidth,
          }));

        return (
          <Box component="li" key={rowKey(row)} sx={{ minWidth: 0 }}>
            <DataTableMobileCard
              title={mobile.title?.(row)}
              subtitle={mobile.subtitle?.(row)}
              status={mobile.status?.(row)}
              fields={fields}
              primaryAction={mobile.primaryAction?.(row)}
              actions={mobile.actions?.(row)}
              onOpen={onRowClick ? () => onRowClick(row) : undefined}
              ariaLabel={mobile.ariaLabel?.(row)}
            />
          </Box>
        );
      })}
    </Stack>
  );
}

export default function DataTable<T>({
  rows,
  rowKey,
  columns,
  mobile,
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
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const { useMobileTableCards } = useAppBreakpoint();
  const { ref: overflowRef, overflowing } = useHorizontalOverflow<HTMLDivElement>();
  const colCount = columns.length;
  const emptyDisplay =
    !loading && rows.length === 0
      ? (emptyState ?? { message: t(DATATABLE_DEFAULT_EMPTY_MESSAGE_KEY) })
      : null;
  const showEmpty = Boolean(emptyDisplay);
  const useCards = useMobileTableCards && (mobile.mode === 'card' || mobile.mode === 'key-value' || mobile.mode === 'comparison');
  const showScrollHint =
    useMobileTableCards &&
    (mobile.mode === 'horizontal-scroll' || mobile.mode === 'log-view') &&
    mobile.showScrollHint !== false &&
    overflowing &&
    !loading &&
    !showEmpty;

  if (useCards) {
    return (
      <Box data-testid={testId} sx={{ width: '100%', maxWidth: '100%', minWidth: 0 }} aria-busy={loading}>
        {loading ? (
          <Stack spacing={1.5}>
            {Array.from({ length: skeletonRows }).map((_, i) => (
              <Skeleton key={`msk-${i}`} variant="rounded" height={104} />
            ))}
          </Stack>
        ) : showEmpty && emptyDisplay ? (
          <Paper variant="outlined" sx={{ borderRadius: 1 }}>
            <Box sx={{ p: 2 }}>
              <EmptyState title={emptyDisplay.title} message={emptyDisplay.message} action={emptyDisplay.action} padding={3} />
            </Box>
          </Paper>
        ) : (
          <MobileCards rows={rows} rowKey={rowKey} mobile={mobile} onRowClick={onRowClick} />
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
      {showScrollHint ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
          {t('table.scroll_hint')}
        </Typography>
      ) : null}
      <TableContainer
        ref={overflowRef}
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
                <TableCell key={col.id} align={col.align ?? 'left'} sx={col.width != null ? { width: col.width } : undefined}>
                  {col.sortable && sort ? (
                    <TableSortLabel
                      active={sort.sortBy === col.id}
                      direction={sort.sortBy === col.id ? sort.sortDir : 'asc'}
                      onClick={() => {
                        const active = sort.sortBy === col.id;
                        const nextDir: DataTableSortDirection = active && sort.sortDir === 'asc' ? 'desc' : 'asc';
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
                    <EmptyState title={emptyDisplay.title} message={emptyDisplay.message} action={emptyDisplay.action} padding={3} />
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
