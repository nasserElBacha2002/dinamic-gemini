/**
 * Reusable UI foundation — structural and state components.
 * Use for consistent page layout, loading, empty, error, and status presentation.
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
export { default as StatusChip } from './StatusChip';
export type { StatusChipProps, StatusChipColor } from './StatusChip';
export { default as TraceabilityChip } from './TraceabilityChip';
export type { TraceabilityChipProps, TraceabilityStatus } from './TraceabilityChip';
