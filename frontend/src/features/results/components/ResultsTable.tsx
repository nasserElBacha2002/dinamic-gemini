/**
 * Sprint 4.1 / v3.3 — Aisle Results table; primary review opens canonical drawer.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../../i18n';
import type { ResultSummary } from '../types';
import {
  DataTable,
  StatusBadge,
  type DataTablePaginationModel,
  type DataTableSortModel,
} from '../../../components/ui';
import { buildResultsTableColumns } from './resultsTableColumns';
import {
  getReviewStatusLabelForDisplay,
  reviewStatusToBadgeSemanticForDisplay,
} from '../utils/evidenceReviewDisplay';

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') {
    const s = r.sku.trim();
    if (s.toUpperCase() === 'UNKNOWN') return i18n.t('results.sku_unknown');
    return s;
  }
  return i18n.t('common.em_dash');
}

function displayQty(r: ResultSummary): string {
  const value = r.resolvedQty != null && !Number.isNaN(r.resolvedQty) ? r.resolvedQty : r.detectedQty;
  return value != null && !Number.isNaN(value) && value >= 0 ? String(value) : i18n.t('common.em_dash');
}

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
      onRowClick={(r) => onOpenReview(r.id)}
      mobile={{
        mode: 'card',
        title: displaySku,
        ariaLabel: displaySku,
        status: (r) => (
          <StatusBadge
            label={getReviewStatusLabelForDisplay(r.reviewStatus)}
            semantic={reviewStatusToBadgeSemanticForDisplay(r.reviewStatus)}
            variant="outlined"
          />
        ),
        fields: [
          {
            id: 'position_code',
            label: t('results.table_column.position_code'),
            value: (r) => (r.positionCode?.trim() ? r.positionCode : t('common.em_dash')),
          },
          {
            id: 'quantity',
            label: t('results.table_column.quantity'),
            value: displayQty,
          },
        ],
      }}
    />
  );
}
