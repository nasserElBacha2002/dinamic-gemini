/**
 * TableSection — thin composition of SectionCard + optional toolbar + DataTable.
 * Domain-specific headers (KPIs, merge feedback) can use `headerSlot` / `footerSlot`.
 */

import type { ReactNode } from 'react';
import SectionCard, { type SectionCardProps } from './SectionCard';
import DataTable from './DataTable';
import ErrorAlert, { type ErrorAlertProps } from './ErrorAlert';
import type { DataTableProps } from './DataTable';

export interface TableSectionProps<T> {
  title?: string;
  description?: string;
  headerActions?: ReactNode;
  /** Optional content inside the section card, above the toolbar. */
  headerSlot?: ReactNode;
  /** Filter toolbar or custom controls above the table. */
  toolbar?: ReactNode;
  footerSlot?: ReactNode;
  error?: ErrorAlertProps | null;
  /** When true and `error` is set, renders only ErrorAlert (no section card). */
  hideSectionOnError?: boolean;
  /** When true and `error` is set, skips DataTable inside the section. */
  hideTableOnError?: boolean;
  variant?: SectionCardProps['variant'];
  elevation?: SectionCardProps['elevation'];
  /** Passed to the underlying SectionCard for stable test selectors. */
  testId?: string;
  table: DataTableProps<T>;
}

export default function TableSection<T>({
  title,
  description,
  headerActions,
  headerSlot,
  toolbar,
  footerSlot,
  error,
  hideSectionOnError = false,
  hideTableOnError = false,
  variant,
  elevation,
  testId,
  table,
}: TableSectionProps<T>) {
  if (error && hideSectionOnError) {
    return <ErrorAlert {...error} />;
  }

  const showTable = !(error && hideTableOnError);

  return (
    <SectionCard
      title={title}
      subtitle={description}
      actions={headerActions}
      variant={variant}
      elevation={elevation}
      testId={testId}
    >
      {error ? <ErrorAlert {...error} /> : null}
      {headerSlot}
      {toolbar}
      {showTable ? <DataTable<T> {...table} /> : null}
      {footerSlot}
    </SectionCard>
  );
}
