/**
 * Sprint 4.2 — Cross-inventory review queue table (priority, context, row actions).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Link as MuiLink, Typography } from '@mui/material';
import i18n from '../../../i18n';
import { Link as RouterLink } from 'react-router-dom';
import type { ReviewQueueItem } from '../../../api/types';
import {
  DataTable,
  StatusBadge,
  TraceabilityChip,
  type DataTableColumn,
  type DataTablePaginationModel,
  type DataTableSortModel,
} from '../../../components/ui';
import { mapPositionSummaryToResultSummary } from '../../results/mappers/positionToResult';
import { deriveResultPriority } from '../../results/utils/resultPriority';
import {
  getReviewStatusLabel,
  reviewStatusToBadgeSemantic,
} from '../../results/utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../results/utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';
import { pathToAislePositions, pathToInventory } from '../../../constants/appRoutes';

export interface ReviewQueueTableProps {
  rows: ReviewQueueItem[];
  loading?: boolean;
  sort: DataTableSortModel;
  pagination: DataTablePaginationModel;
  /** Canonical review surface: opens the drawer. */
  onOpenReview: (item: ReviewQueueItem) => void;
}

function prioritySemantic(
  tier: number
): 'error' | 'warning' | 'review' | 'neutral' {
  if (tier === 1) return 'error';
  if (tier === 2) return 'warning';
  if (tier === 3) return 'review';
  return 'neutral';
}

function displaySku(item: ReviewQueueItem): string {
  const r = mapPositionSummaryToResultSummary(item.position);
  const s = r.sku;
  if (s != null && String(s).trim() !== '') return String(s).trim();
  return i18n.t('common.em_dash');
}

function displayQty(item: ReviewQueueItem): string {
  const r = mapPositionSummaryToResultSummary(item.position);
  const v = r.resolvedQty ?? r.detectedQty;
  if (v != null && !Number.isNaN(v) && v >= 0) return String(v);
  return i18n.t('common.em_dash');
}

export default function ReviewQueueTable({
  rows,
  loading,
  sort,
  pagination,
  onOpenReview,
}: ReviewQueueTableProps) {
  const { t } = useTranslation();
  const dash = i18n.t('common.em_dash');
  const columns = useMemo<DataTableColumn<ReviewQueueItem>[]>(() => {
    return [
      {
        id: 'priority',
        label: t('review_queue.column_priority'),
        width: 88,
        sortable: true,
        cell: (item) => {
          const r = mapPositionSummaryToResultSummary(item.position);
          const p = deriveResultPriority(r);
          return (
            <StatusBadge label={p.label} semantic={prioritySemantic(p.tier)} variant="outlined" />
          );
        },
      },
      {
        id: 'sku',
        label: t('common.sku'),
        cell: (item) => {
          const label = displaySku(item);
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
              onClick={() => onOpenReview(item)}
              aria-label={t('review_queue_table.review_aria', { sku: label })}
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
        id: 'qty',
        label: t('review_queue.column_quantity'),
        align: 'right',
        cell: (item) => displayQty(item),
      },
      {
        id: 'confidence',
        label: t('common.confidence'),
        align: 'right',
        sortable: true,
        cell: (item) =>
          item.position.confidence != null ? `${(item.position.confidence * 100).toFixed(0)}%` : dash,
      },
      {
        id: 'traceability',
        label: t('common.traceability'),
        cell: (item) => {
          const r = mapPositionSummaryToResultSummary(item.position);
          return (
            <TraceabilityChip
              status={visibleTraceabilityToApiStatus(r.traceabilityStatus)}
              size="small"
              variant="outlined"
            />
          );
        },
      },
      {
        id: 'review_status',
        label: t('results.table_column.review_status'),
        cell: (item) => {
          const r = mapPositionSummaryToResultSummary(item.position);
          return (
            <StatusBadge
              label={getReviewStatusLabel(r.reviewStatus)}
              semantic={reviewStatusToBadgeSemantic(r.reviewStatus)}
              variant="outlined"
            />
          );
        },
      },
      {
        id: 'inventory',
        label: t('common.inventory'),
        cell: (item) => (
          <MuiLink
            component={RouterLink}
            to={pathToInventory(item.inventory_id)}
            variant="body2"
            underline="hover"
            color="primary"
          >
            {item.inventory_name}
          </MuiLink>
        ),
      },
      {
        id: 'aisle',
        label: t('common.aisle'),
        cell: (item) => (
          <MuiLink
            component={RouterLink}
            to={pathToAislePositions(item.inventory_id, item.position.aisle_id)}
            variant="body2"
            underline="hover"
            color="primary"
          >
            {item.aisle_code}
          </MuiLink>
        ),
      },
      {
        id: 'updated_at',
        label: t('common.updated'),
        sortable: true,
        cell: (item) => (
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.85rem' }}>
            {formatDate(item.position.updated_at)}
          </Typography>
        ),
      },
    ];
  }, [onOpenReview, t, dash]);

  return (
    <DataTable<ReviewQueueItem>
      rows={rows}
      rowKey={(item) => `${item.inventory_id}-${item.position.id}`}
      columns={columns}
      stickyHeader
      size="medium"
      rowHover
      loading={loading}
      sort={sort}
      pagination={pagination}
      emptyState={{
        title: t('review_queue_table.empty_title'),
        message: t('review_queue_table.empty_message'),
      }}
    />
  );
}
