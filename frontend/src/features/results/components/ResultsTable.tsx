/**
 * Sprint 4.1 — Aisle Results table: priority, SKU, quantity, review status, traceability, confidence, evidence, updated, action.
 */

import { useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import type { ResultSummary } from '../types';
import {
  DataTable,
  StatusBadge,
  RowActionMenu,
  TraceabilityChip,
  type DataTableColumn,
  type DataTablePaginationModel,
} from '../../../components/ui';
import {
  getReviewStatusLabel,
  reviewStatusToBadgeSemantic,
} from '../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';
import { deriveResultPriority } from '../utils/resultPriority';

export interface ResultsTableProps {
  results: ResultSummary[];
  onOpenDetail: (resultId: string) => void;
  /** Client-side pagination (Sprint 4.1) until the results list API is pageable. */
  pagination?: DataTablePaginationModel;
  loading?: boolean;
}

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') return r.sku.trim();
  return '—';
}

function displayQty(r: ResultSummary): string {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty) ? r.resolvedQty : r.detectedQty;

  if (value != null && !Number.isNaN(value) && value >= 0) {
    return String(value);
  }
  return '—';
}

function prioritySemantic(
  tier: number
): 'error' | 'warning' | 'review' | 'neutral' {
  if (tier === 1) return 'error';
  if (tier === 2) return 'warning';
  if (tier === 3) return 'review';
  return 'neutral';
}

export default function ResultsTable({ results, onOpenDetail, pagination, loading }: ResultsTableProps) {
  const columns = useMemo<DataTableColumn<ResultSummary>[]>(() => {
    return [
      {
        id: 'priority',
        label: 'Priority',
        width: 88,
        cell: (r) => {
          const p = deriveResultPriority(r);
          return (
            <StatusBadge label={p.label} semantic={prioritySemantic(p.tier)} variant="outlined" />
          );
        },
      },
      {
        id: 'sku',
        label: 'SKU',
        cell: (r) => <Box component="span" sx={{ fontWeight: 500 }}>{displaySku(r)}</Box>,
      },
      {
        id: 'qty',
        label: 'Quantity',
        align: 'right',
        cell: (r) => displayQty(r),
      },
      {
        id: 'review_status',
        label: 'Review status',
        cell: (r) => (
          <StatusBadge
            label={getReviewStatusLabel(r.reviewStatus)}
            semantic={reviewStatusToBadgeSemantic(r.reviewStatus)}
            variant="outlined"
          />
        ),
      },
      {
        id: 'traceability',
        label: 'Traceability',
        cell: (r) => (
          <TraceabilityChip
            status={visibleTraceabilityToApiStatus(r.traceabilityStatus)}
            size="small"
            variant="outlined"
          />
        ),
      },
      {
        id: 'confidence',
        label: 'Confidence',
        align: 'right',
        cell: (r) => (r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : '—'),
      },
      {
        id: 'evidence',
        label: 'Evidence',
        cell: (r) => (
          <StatusBadge
            label={r.hasEvidence ? 'Present' : 'Missing'}
            semantic={r.hasEvidence ? 'success' : 'warning'}
            variant="outlined"
          />
        ),
      },
      {
        id: 'updated',
        label: 'Updated',
        cell: (r) => (
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
            {formatDate(r.updatedAt)}
          </Typography>
        ),
      },
      {
        id: 'action',
        label: 'Action',
        align: 'right',
        width: 56,
        cell: (r) => (
          <RowActionMenu
            ariaLabel={`Actions for result ${displaySku(r)}`}
            items={[
              {
                id: 'review',
                label: 'Review',
                onClick: () => onOpenDetail(r.id),
              },
            ]}
          />
        ),
      },
    ];
  }, [onOpenDetail]);

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
    />
  );
}
