/**
 * Epic 4 — Summary card for Result Detail (SKU, quantity, status, traceability, confidence).
 * Phase 6: Current final state and count-origin visibility per POSITION_RESULT_CONTRACT.
 * Visible quantity = corrected_quantity ?? qty; show system quantity when override exists.
 */

import { Paper, Typography, Box } from '@mui/material';
import type { ResultDetail } from '../../types';
import { StatusChip, TraceabilityChip } from '../../../../components/ui';
import { getCountOriginLabel } from '../../utils/countOriginLabel';
import { getReviewStatusLabel, getReviewStatusColor } from '../../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../utils/traceabilityDisplay';
import { formatDate } from '../../../../utils/formatDate';

export interface ResultSummaryCardProps {
  result: ResultDetail;
  /** Tighter layout for the canonical review drawer (single operational column). */
  embedInDrawer?: boolean;
}

function displayStr(value: string | null | undefined): string {
  if (value != null && String(value).trim() !== '') return String(value).trim();
  return '—';
}

/** Coerce to finite number or null; avoids NaN and mixed string/number. */
function toNumeric(value: unknown): number | null {
  if (value == null) return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export default function ResultSummaryCard({ result, embedInDrawer }: ResultSummaryCardProps) {
  const sku = displayStr(result.sku);

  const correctedQtyNum = toNumeric(result.correctedQty);
  const resolvedQtyNum = toNumeric(result.resolvedQty);
  const systemQtyNum = toNumeric(result.systemQty);

  const visibleQtyNum = correctedQtyNum ?? resolvedQtyNum;
  const hasManualOverride = correctedQtyNum != null;

  const confidenceStr =
    result.confidence != null
      ? `${(result.confidence * 100).toFixed(0)}%`
      : '—';

  return (
    <Paper sx={{ p: embedInDrawer ? 1.5 : 2, mb: embedInDrawer ? 1.5 : 2 }} elevation={embedInDrawer ? 0 : undefined}>
      {!embedInDrawer ? (
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
          Result summary
        </Typography>
      ) : (
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5, display: 'block', mb: 1 }}>
          Summary
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary" display="block">
        SKU
      </Typography>
      <Typography variant={embedInDrawer ? 'subtitle1' : 'h6'} sx={{ fontWeight: 600 }}>
        {sku}
      </Typography>

      <Box sx={{ display: 'flex', gap: 2, mt: 1.5, flexWrap: 'wrap' }}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Current quantity
          </Typography>
          <Typography variant="body1">
            {visibleQtyNum != null ? String(visibleQtyNum) : '—'}
          </Typography>
        </Box>
        {hasManualOverride && systemQtyNum != null && (
          <Box>
            <Typography variant="caption" color="text.secondary">
              System quantity
            </Typography>
            <Typography variant="body1">{String(systemQtyNum)}</Typography>
          </Box>
        )}
      </Box>

      {hasManualOverride && (
        <Typography variant="caption" color="primary.main" display="block" sx={{ mt: 0.5 }}>
          Manual override applied
        </Typography>
      )}

      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
        Count origin: {getCountOriginLabel(result)}
      </Typography>

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
          label={`${confidenceStr} confidence`}
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
