/**
 * Sprint 4.1 / v3.3 — Aisle Results table; primary review opens canonical drawer.
 */

import { useMemo } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Box, Button, Typography } from '@mui/material';
import i18n from '../../../i18n';
import type { ResultSummary } from '../types';
import {
  DataTable,
  StatusBadge,
  TraceabilityChip,
  type DataTableColumn,
  type DataTablePaginationModel,
  type DataTableSortModel,
} from '../../../components/ui';
import {
  getImageMismatchEvidenceLabel,
  hasImageMismatchEvidenceIssue,
  getReviewStatusLabelForDisplay,
  reviewStatusToBadgeSemanticForDisplay,
} from '../utils/evidenceReviewDisplay';
import { visibleTraceabilityToApiStatus } from '../utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';
import { deriveResultPriority } from '../utils/resultPriority';

export interface ResultsTableProps {
  results: ResultSummary[];
  /** Canonical review: opens drawer on list parent. */
  onOpenReview: (resultId: string) => void;
  pagination?: DataTablePaginationModel;
  loading?: boolean;
  /** Client-side column sort (parent applies `sortDataTableRows` before pagination). */
  sort?: DataTableSortModel;
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

function sortQtyValue(r: ResultSummary): number | null {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty) ? r.resolvedQty : r.detectedQty;
  if (value != null && !Number.isNaN(value) && value >= 0) {
    return value;
  }
  return null;
}

function prioritySemantic(
  tier: number
): 'error' | 'warning' | 'review' | 'neutral' {
  if (tier === 1) return 'error';
  if (tier === 2) return 'warning';
  if (tier === 3) return 'review';
  return 'neutral';
}

export function buildResultsTableColumns(params: {
  t: TFunction;
  dash: string;
  onOpenReview: (resultId: string) => void;
}): DataTableColumn<ResultSummary>[] {
  const { t, dash, onOpenReview } = params;
  return [
    {
      id: 'priority',
      label: t('results.table_column.priority'),
      width: 88,
      sortable: true,
      sortType: 'number',
      sortAccessor: (r) => deriveResultPriority(r).tier,
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
      sortable: true,
      sortType: 'string',
      sortAccessor: (r) => (r.sku ?? '').trim().toLowerCase(),
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
      sortable: true,
      sortType: 'string',
      sortAccessor: (r) => (r.positionCode ?? '').trim().toLowerCase(),
      cell: (r) => (r.positionCode != null && r.positionCode.trim() !== '' ? r.positionCode : dash),
    },
    {
      id: 'qty',
      label: t('results.table_column.quantity'),
      align: 'right',
      sortable: true,
      sortType: 'number',
      sortAccessor: (r) => sortQtyValue(r),
      cell: (r) => displayQty(r),
    },
    {
      id: 'review_status',
      label: t('results.table_column.review_status'),
      sortable: true,
      sortType: 'string',
      sortAccessor: (r) => getReviewStatusLabelForDisplay(r.reviewStatus),
      cell: (r) => (
        <StatusBadge
          label={getReviewStatusLabelForDisplay(r.reviewStatus)}
          semantic={reviewStatusToBadgeSemanticForDisplay(r.reviewStatus)}
          variant="outlined"
        />
      ),
    },
    {
      id: 'traceability',
      label: t('common.traceability'),
      sortable: true,
      sortType: 'string',
      sortAccessor: (r) =>
        hasImageMismatchEvidenceIssue(r.reviewStatus)
          ? `mismatch:${r.traceabilityStatus}`
          : r.traceabilityStatus,
      cell: (r) => {
        const imageMismatch = hasImageMismatchEvidenceIssue(r.reviewStatus);
        return (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, alignItems: 'flex-start' }}>
            <TraceabilityChip
              status={visibleTraceabilityToApiStatus(r.traceabilityStatus)}
              size="small"
              variant="outlined"
            />
            {imageMismatch ? (
              <StatusBadge
                label={getImageMismatchEvidenceLabel()}
                semantic="warning"
                variant="outlined"
              />
            ) : null}
          </Box>
        );
      },
    },
    {
      id: 'confidence',
      label: t('common.confidence'),
      align: 'right',
      sortable: true,
      sortType: 'number',
      sortAccessor: (r) => r.confidence,
      cell: (r) => (r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : dash),
    },
    {
      id: 'evidence',
      label: t('results.table_column.evidence'),
      sortable: true,
      sortType: 'boolean',
      sortAccessor: (r) => r.hasEvidence,
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
      sortable: true,
      sortType: 'date',
      sortAccessor: (r) => r.updatedAt,
      cell: (r) => (
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
          {formatDate(r.updatedAt)}
        </Typography>
      ),
    },
  ];
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
