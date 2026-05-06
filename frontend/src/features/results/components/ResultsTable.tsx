/**
 * Sprint 4.1 / v3.3 — Aisle Results table; primary review opens canonical drawer.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import i18n from '../../../i18n';
import type { ResultSummary } from '../types';
import {
  DataTable,
  StatusBadge,
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
  /** Canonical review: opens drawer on list parent. */
  onOpenReview: (resultId: string) => void;
  pagination?: DataTablePaginationModel;
  loading?: boolean;
}

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') {
    const s = r.sku.trim();
    if (s.toUpperCase() === 'UNKNOWN') return i18n.t('results.sku_unknown');
    return s;
  }
  return i18n.t('common.em_dash');
}

function displayQty(r: ResultSummary): string {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty) ? r.resolvedQty : r.detectedQty;

  if (value != null && !Number.isNaN(value) && value >= 0) {
    return String(value);
  }
  return i18n.t('common.em_dash');
}

function prioritySemantic(
  tier: number
): 'error' | 'warning' | 'review' | 'neutral' {
  if (tier === 1) return 'error';
  if (tier === 2) return 'warning';
  if (tier === 3) return 'review';
  return 'neutral';
}

export default function ResultsTable({
  results,
  onOpenReview,
  pagination,
  loading,
}: ResultsTableProps) {
  const { t } = useTranslation();
  const dash = i18n.t('common.em_dash');
  const columns = useMemo<DataTableColumn<ResultSummary>[]>(() => {
    return [
      {
        id: 'priority',
        label: t('results.table_column.priority'),
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
        label: t('results.table_column.sku'),
        cell: (r) => {
          const label = displaySku(r);
          if (label === dash) {
            return (
              <Typography variant="body2" color="text.secondary" component="span">
                {label}
              </Typography>
            );
          }
          return (
            <Button
              variant="text"
              size="small"
              onClick={() => onOpenReview(r.id)}
              aria-label={t('results.table_review_aria', { sku: label })}
              sx={{
                fontWeight: 650,
                textTransform: 'none',
                px: 0,
                minWidth: 0,
                justifyContent: 'flex-start',
                color: 'text.primary',
                '&:hover': { textDecoration: 'underline', backgroundColor: 'transparent' },
              }}
            >
              {label}
            </Button>
          );
        },
      },
      {
        id: 'position_code',
        label: t('results.table_column.position_code'),
        cell: (r) => (r.positionCode != null && r.positionCode.trim() !== '' ? r.positionCode : dash),
      },
      {
        id: 'qty',
        label: t('results.table_column.quantity'),
        align: 'right',
        cell: (r) => displayQty(r),
      },
      {
        id: 'review_status',
        label: t('results.table_column.review_status'),
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
        label: t('common.traceability'),
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
        label: t('common.confidence'),
        align: 'right',
        cell: (r) => (r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : dash),
      },
      {
        id: 'evidence',
        label: t('results.table_column.evidence'),
        cell: (r) => (
          <StatusBadge
            label={r.hasEvidence ? t('results.evidence_present') : t('results.evidence_missing')}
            semantic={r.hasEvidence ? 'success' : 'warning'}
            variant="outlined"
          />
        ),
      },
      {
        id: 'updated',
        label: t('results.table_column.updated'),
        cell: (r) => (
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
            {formatDate(r.updatedAt)}
          </Typography>
        ),
      },
    ];
  }, [onOpenReview, t, dash]);

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
