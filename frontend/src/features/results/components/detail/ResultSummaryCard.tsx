/**
 * Epic 4 — Summary card for Result Detail (SKU, quantity, status, traceability, confidence).
 */

import { Paper, Typography, Box } from '@mui/material';
import type { ResultDetail } from '../../types';
import { StatusChip, TraceabilityChip } from '../../../../components/ui';
import { getReviewStatusLabel, getReviewStatusColor } from '../../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../utils/traceabilityDisplay';
import { formatDate } from '../../../../utils/formatDate';

export interface ResultSummaryCardProps {
  result: ResultDetail;
}

function displayStr(value: string | null | undefined): string {
  if (value != null && String(value).trim() !== '') return String(value).trim();
  return '—';
}

export default function ResultSummaryCard({ result }: ResultSummaryCardProps) {
  const sku = displayStr(result.sku);
  const qty =
    result.correctedQty != null && !Number.isNaN(result.correctedQty)
      ? String(result.correctedQty)
      : result.resolvedQty != null && !Number.isNaN(result.resolvedQty)
      ? String(result.resolvedQty)
      : '—';
  const correctedQty =
    result.correctedQty != null && !Number.isNaN(result.correctedQty)
      ? String(result.correctedQty)
      : null;
  const confidence =
    result.confidence != null
      ? `${(result.confidence * 100).toFixed(0)}%`
      : '—';

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle2" color="text.secondary">
        SKU
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        {sku}
      </Typography>

      <Box sx={{ display: 'flex', gap: 2, mt: 1.5, flexWrap: 'wrap' }}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Qty
          </Typography>
          <Typography variant="body1">{qty}</Typography>
        </Box>
        {correctedQty != null && (
          <Box>
            <Typography variant="caption" color="text.secondary">
              Corrected qty
            </Typography>
            <Typography variant="body1">{correctedQty}</Typography>
          </Box>
        )}
      </Box>

      <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <StatusChip
          label={getReviewStatusLabel(result.reviewStatus)}
          color={getReviewStatusColor(result.reviewStatus)}
          size="small"
          variant="outlined"
        />
        <TraceabilityChip
          status={visibleTraceabilityToApiStatus(result.traceabilityStatus)}
          size="small"
          variant="outlined"
        />
        <StatusChip
          label={`${confidence} confidence`}
          variant="outlined"
          size="small"
        />
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
        Updated: {formatDate(result.updatedAt)}
      </Typography>
    </Paper>
  );
}
