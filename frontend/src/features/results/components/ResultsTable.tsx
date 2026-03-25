/**
 * Epic 3 — Result-centric table for the Results overview.
 * Columns: SKU, Qty, Traceability, Status, Confidence, Evidence, (Updated), Action.
 *
 * **Sprint 2.4 — partial `DataTable` adoption:** this component uses the shared shell (density, sticky header, hover)
 * but **does not** pass `DataTable` loading, empty, or pagination props. `AislePositionsPage` owns loading / empty /
 * filtered-empty UX and loads results in one chunk for client-side quick filters — a full server-driven table is
 * deferred until the results list contract is wired for paged/sorted fetches.
 */

import { useMemo } from 'react';
import { Box, Button, Tooltip, Typography } from '@mui/material';
import type { ResultSummary } from '../types';
import { DataTable, StatusChip, TraceabilityChip, type DataTableColumn } from '../../../components/ui';
import { getReviewStatusLabel, getReviewStatusColor } from '../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';

export interface ResultsTableProps {
  results: ResultSummary[];
  onOpenDetail: (resultId: string) => void;
  /** Optional: show updated-at in a subtle way. */
  showUpdatedAt?: boolean;
}

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') return r.sku.trim();
  return '—';
}

function displayQty(r: ResultSummary): string {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty)
      ? r.resolvedQty
      : r.detectedQty;

  if (value != null && !Number.isNaN(value) && value >= 0) {
    return String(value);
  }
  return '—';
}

function displayEvidence(r: ResultSummary): string {
  return r.hasEvidence ? 'Yes' : '—';
}

export default function ResultsTable({ results, onOpenDetail, showUpdatedAt = false }: ResultsTableProps) {
  const columns = useMemo<DataTableColumn<ResultSummary>[]>(() => {
    const cols: DataTableColumn<ResultSummary>[] = [
      {
        id: 'sku',
        label: 'SKU',
        cell: (r) => <Box component="span" sx={{ fontWeight: 500 }}>{displaySku(r)}</Box>,
      },
      {
        id: 'qty',
        label: 'Qty',
        align: 'right',
        cell: (r) => displayQty(r),
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
        id: 'status',
        label: 'Status',
        cell: (r) => (
          <StatusChip
            label={getReviewStatusLabel(r.reviewStatus)}
            color={getReviewStatusColor(r.reviewStatus)}
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
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
            {displayEvidence(r)}
          </Typography>
        ),
      },
    ];
    if (showUpdatedAt) {
      cols.push({
        id: 'updated',
        label: 'Updated',
        cell: (r) => (
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
            {formatDate(r.updatedAt)}
          </Typography>
        ),
      });
    }
    cols.push({
      id: 'action',
      label: 'Action',
      align: 'right',
      width: 100,
      cell: (r) => (
        <Tooltip title="Open result detail">
          <Button variant="outlined" size="small" onClick={() => onOpenDetail(r.id)}>
            Review
          </Button>
        </Tooltip>
      ),
    });
    return cols;
  }, [showUpdatedAt, onOpenDetail]);

  return (
    <DataTable<ResultSummary>
      rows={results}
      rowKey={(r) => r.id}
      columns={columns}
      stickyHeader
      size="small"
    />
  );
}
