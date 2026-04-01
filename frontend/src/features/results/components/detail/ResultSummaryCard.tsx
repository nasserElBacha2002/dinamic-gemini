/**
 * Epic 4 — Summary section for Result Detail (quantity, origin, status, traceability, confidence).
 * Revised in Phase 3: Simplified for better hierarchy in the review drawer.
 */

import { Typography, Box } from '@mui/material';
import type { ResultDetail } from '../../types';
import { StatusChip, TraceabilityChip } from '../../../../components/ui';
import { getCountOriginLabel } from '../../utils/countOriginLabel';
import { getReviewStatusLabel, getReviewStatusColor } from '../../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../../utils/traceabilityDisplay';
import { formatDate } from '../../../../utils/formatDate';

export interface ResultSummaryCardProps {
  result: ResultDetail;
}

/** Coerce to finite number or null; avoids NaN and mixed string/number. */
function toNumeric(value: unknown): number | null {
  if (value == null) return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export default function ResultSummaryCard({ result }: ResultSummaryCardProps) {
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
    <Box sx={{ px: 0.5 }}>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2.5, mb: 2 }}>
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Current quantity
          </Typography>
          <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.2 }}>
            {visibleQtyNum != null ? String(visibleQtyNum) : '—'}
          </Typography>
          {hasManualOverride && (
             <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600, mt: 0.5, display: 'block' }}>
               Manual override
             </Typography>
          )}
        </Box>
        
        {hasManualOverride && systemQtyNum != null && (
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              System original
            </Typography>
            <Typography variant="body1" fontWeight={500}>{String(systemQtyNum)}</Typography>
          </Box>
        )}

        <Box sx={{ gridColumn: hasManualOverride ? undefined : 'span 1' }}>
           <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Count origin
          </Typography>
          <Typography variant="body2" fontWeight={500}>
            {getCountOriginLabel(result)}
          </Typography>
        </Box>

        <Box>
           <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25, fontWeight: 500, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Last update
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {formatDate(result.updatedAt)}
          </Typography>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
        <StatusChip
          label={getReviewStatusLabel(result.reviewStatus)}
          color={getReviewStatusColor(result.reviewStatus)}
          size="small"
          variant="filled"
        />
        <TraceabilityChip
          status={visibleTraceabilityToApiStatus(result.traceabilityStatus)}
          size="small"
        />
        <StatusChip
          label={`${confidenceStr} confidence`}
          variant="outlined"
          size="small"
        />
      </Box>
    </Box>
  );
}
