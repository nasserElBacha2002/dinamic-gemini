/**
 * Sprint 4.1 / v3.3 — Aisle Results table; primary review opens canonical drawer.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../../i18n';
import type { ResultSummary } from '../types';
import {
  DataTable,
  type DataTablePaginationModel,
  type DataTableSortModel,
} from '../../../components/ui';
import { buildResultsTableColumns } from './resultsTableColumns';

export type { DataTableColumn } from '../../../components/ui';
export { buildResultsTableColumns } from './resultsTableColumns';

export interface ResultsTableProps {
  results: ResultSummary[];
  /** Canonical review: opens drawer on list parent. */
  onOpenReview: (resultId: string) => void;
  pagination?: DataTablePaginationModel;
  loading?: boolean;
  /** Client-side column sort (parent applies `sortDataTableRows` before pagination). */
  sort?: DataTableSortModel;
}

export default function ResultsTable({
  results,
  onOpenReview,
  pagination,
  loading,
  sort,
}: ResultsTableProps) {
  const { t } = useTranslation();
  const dash = i18n.t('common.em_dash');
  const columns = useMemo(
    () => buildResultsTableColumns({ t, dash, onOpenReview }),
    [onOpenReview, t, dash]
  );

  return (
    <DataTable<ResultSummary>
      rows={results}
      rowKey={(r) => r.id}
      columns={columns}
      stickyHeader
      size="small"
      rowHover
      loading={loading}
      pagination={pagination}
      sort={sort}
    />
  );
}
