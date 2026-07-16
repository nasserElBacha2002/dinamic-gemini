/**
 * Reusable UI base — Sprint 2.3 (Re diseño 3.3 §8.x).
 * Structural primitives: shell/; operational building blocks live here.
 *
 * **Dialogs:** `BaseDialog` (generic) → `ConfirmDialog` composes it; `WizardModal` is a separate stepper shell.
 * **Status:** `StatusBadge` is the **default for new tables/lists** when status maps to redesign semantics (§8.4).
 *   `StatusChip` stays appropriate where **mapper helpers already emit MUI chip colors** (e.g. review status in results).
 * **Tables (Sprint 2.4):** `DataTable` — server sort/pagination, loading skeleton, empty fallback; compose with `TableSection` or `SectionCard` + `FilterToolbar`.
 * **KPI bands (F7.1):** `KpiCardBand` — layout presets around `KpiCard` (flex strip vs responsive grids); no domain data.
 * **Drawers (F7.3):** `DrawerHeader` — sticky title row + close for right-anchor drawers; no domain state.
 * **Metrics:** Prefer `KpiCard` + `KpiCardBand` for KPI bands; page shells stay in routes/features (`PageHeader`, `SectionCard`, etc.).
 */

export { default as LoadingBlock } from './LoadingBlock';
export type { LoadingBlockProps } from './LoadingBlock';
export { default as EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { default as ErrorAlert } from './ErrorAlert';
export type { ErrorAlertProps } from './ErrorAlert';
export { default as ImageViewer } from './ImageViewer';
export type { ImageViewerProps } from './ImageViewer';
export { default as ImageAssetCard } from './ImageAssetCard';
export type { ImageAssetCardProps } from './ImageAssetCard';
export { default as ImagePreviewDialog } from './ImagePreviewDialog';
export type { ImagePreviewDialogProps } from './ImagePreviewDialog';

export { default as KpiCard } from './KpiCard';
export type { KpiCardProps } from './KpiCard';
export { default as KpiCardBand } from './KpiCardBand';
export type { KpiCardBandProps, KpiCardBandVariant } from './KpiCardBand';
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
export { default as DrawerHeader } from './DrawerHeader';
export type { DrawerHeaderProps } from './DrawerHeader';

export { default as FilterToolbar } from './FilterToolbar';
export type { FilterToolbarProps } from './FilterToolbar';
export { default as TableSearchField } from './TableSearchField';
export type { TableSearchFieldProps } from './TableSearchField';
export { default as RowActionMenu } from './RowActionMenu';
export type { RowActionMenuProps, RowActionMenuItem } from './RowActionMenu';

export { default as DataTable } from './DataTable';
export type {
  DataTableColumn,
  DataTablePaginationModel,
  DataTableProps,
  DataTableSortDirection,
  DataTableSortModel,
  DataTableSortType,
} from './DataTable';
export { sortDataTableRows } from './dataTableSort';
export { default as TableSection } from './TableSection';
export type { TableSectionProps } from './TableSection';

export { default as DataTableMobileCard } from './DataTableMobileCard';
export type { DataTableMobileCardProps } from './DataTableMobileCard';

export { default as PhotoUploadProgressDialog } from './PhotoUploadProgressDialog';
export type { PhotoUploadProgressDialogProps } from './PhotoUploadProgressDialog';

export { AppSnackbarProvider } from './AppSnackbarProvider';
export { useAppSnackbar } from './useAppSnackbar';
export { useErrorSnackbar } from './useErrorSnackbar';
export type { AppSnackbarSeverity } from './appSnackbarContext';
