/**
 * Sprint 4.2 — Compact review snapshot before full detail (no mutations; Sprint 4.4 adds quick actions).
 */

import { Box, Button, Divider, Drawer, Stack, Typography } from '@mui/material';
import type { ReviewQueueItem } from '../../../api/types';
import { StatusBadge, TraceabilityChip } from '../../../components/ui';
import { mapPositionSummaryToResultSummary } from '../../results/mappers/positionToResult';
import {
  getReviewStatusLabel,
  reviewStatusToBadgeSemantic,
} from '../../results/utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../results/utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';

export interface QuickReviewDrawerProps {
  open: boolean;
  row: ReviewQueueItem | null;
  onClose: () => void;
  onOpenFullReview: () => void;
}

function snapshotSku(row: ReviewQueueItem): string {
  const s = row.position.sku;
  if (s != null && String(s).trim() !== '') return String(s).trim();
  return '—';
}

function snapshotQty(row: ReviewQueueItem): string {
  const r = mapPositionSummaryToResultSummary(row.position);
  const v = r.resolvedQty ?? r.detectedQty;
  if (v != null && !Number.isNaN(v) && v >= 0) return String(v);
  return '—';
}

function snapshotConfidence(row: ReviewQueueItem): string {
  const c = row.position.confidence;
  return c != null ? `${(c * 100).toFixed(0)}%` : '—';
}

export default function QuickReviewDrawer({
  open,
  row,
  onClose,
  onOpenFullReview,
}: QuickReviewDrawerProps) {
  const result = row ? mapPositionSummaryToResultSummary(row.position) : null;
  const hasEvidence = result?.hasEvidence ?? false;

  if (!row || !result) {
    return (
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, p: 2 } }}
      >
        <Typography variant="body2" color="text.secondary">
          Select a row to preview.
        </Typography>
      </Drawer>
    );
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 } }}
    >
      <Typography variant="subtitle1" component="h2" fontWeight={600}>
        Quick review
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {row.inventory_name} · {row.aisle_code}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Updated {formatDate(row.position.updated_at)}
      </Typography>

      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          p: 1.5,
          bgcolor: 'action.hover',
        }}
      >
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
          Evidence
        </Typography>
        <StatusBadge
          label={hasEvidence ? 'Present' : 'Missing'}
          semantic={hasEvidence ? 'success' : 'warning'}
          variant="outlined"
        />
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
          Open full review for image evidence.
        </Typography>
      </Box>

      <Divider />

      <Stack spacing={1}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            SKU
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {snapshotSku(row)}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            Quantity
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {snapshotQty(row)}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            Confidence
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {snapshotConfidence(row)}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            Traceability
          </Typography>
          <TraceabilityChip
            status={visibleTraceabilityToApiStatus(result.traceabilityStatus)}
            size="small"
            variant="outlined"
          />
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            Review status
          </Typography>
          <StatusBadge
            label={getReviewStatusLabel(result.reviewStatus)}
            semantic={reviewStatusToBadgeSemantic(result.reviewStatus)}
            variant="outlined"
          />
        </Box>
      </Stack>

      <Box sx={{ mt: 'auto', pt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button variant="contained" onClick={onOpenFullReview} fullWidth sx={{ flex: '1 1 160px' }}>
          Open full review
        </Button>
        <Button variant="text" onClick={onClose} sx={{ flex: '0 0 auto' }}>
          Close
        </Button>
      </Box>

      <Typography variant="caption" color="text.secondary" display="block">
        Confirm or change this result in full review. Inline quick actions — Sprint 4.4.
      </Typography>
    </Drawer>
  );
}
