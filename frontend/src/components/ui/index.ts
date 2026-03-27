/**
 * Reusable UI base — Sprint 2.3 (Re diseño 3.3 §8.x).
 * Structural primitives: shell/; operational building blocks live here.
 *
 * **Dialogs:** `BaseDialog` (generic) → `ConfirmDialog` composes it; `WizardModal` is a separate stepper shell.
 * **Status:** `StatusBadge` is the **default for new tables/lists** when status maps to redesign semantics (§8.4).
 *   `StatusChip` stays appropriate where **mapper helpers already emit MUI chip colors** (e.g. review status in results).
 * **Tables (Sprint 2.4):** `DataTable` — server sort/pagination, loading skeleton, empty fallback; compose with `SectionCard` + `FilterToolbar`.
 */

export { default as PageLayout } from './PageLayout';
export type { PageLayoutProps } from './PageLayout';
export { default as LoadingBlock } from './LoadingBlock';
export type { LoadingBlockProps } from './LoadingBlock';
export { default as EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { default as ErrorAlert } from './ErrorAlert';
export type { ErrorAlertProps } from './ErrorAlert';

export { default as StatCard } from './StatCard';
export type { StatCardProps } from './StatCard';
export { default as KpiCard } from './KpiCard';
export type { KpiCardProps } from './KpiCard';
export { default as SectionCard } from './SectionCard';
export type { SectionCardProps } from './SectionCard';

export { default as StatusChip } from './StatusChip';
export type { StatusChipProps, StatusChipColor } from './StatusChip';
export { default as StatusBadge } from './StatusBadge';
export type { StatusBadgeProps, StatusBadgeSemantic } from './StatusBadge';
export { default as TraceabilityChip } from './TraceabilityChip';
export type { TraceabilityChipProps, ApiTraceabilityStatus } from './TraceabilityChip';

export { default as BaseDialog } from './BaseDialog';
export type { BaseDialogProps } from './BaseDialog';
export { default as ConfirmDialog } from './ConfirmDialog';
export type { ConfirmDialogProps } from './ConfirmDialog';
export { default as WizardModal } from './WizardModal';
export type { WizardModalProps } from './WizardModal';

export { default as FilterToolbar } from './FilterToolbar';
export type { FilterToolbarProps } from './FilterToolbar';
export { default as RowActionMenu } from './RowActionMenu';
export type { RowActionMenuProps, RowActionMenuItem } from './RowActionMenu';

export { default as DataTable } from './DataTable';
export type {
  DataTableColumn,
  DataTablePaginationModel,
  DataTableProps,
  DataTableSortDirection,
  DataTableSortModel,
} from './DataTable';

export { AppSnackbarProvider, useAppSnackbar } from './AppSnackbarProvider';
export type { AppSnackbarSeverity } from './AppSnackbarProvider';
