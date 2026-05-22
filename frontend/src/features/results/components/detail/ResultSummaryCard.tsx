/**
 * Epic 4 — Summary section for Result Detail (quantity, origin, status, traceability, confidence).
 * Revised in Phase 3 & Polished in Phase 4: Cohesive "Current State" visual block.
 */

import { Typography, Box } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ResultDetail } from '../../types';
import { StatusChip, TraceabilityChip } from '../../../../components/ui';
import { getCountOriginLabel } from '../../utils/countOriginLabel';
import {
  getImageMismatchEvidenceLabel,
  getReviewStatusColorForDisplay,
  getReviewStatusLabelForDisplay,
  shouldReplaceTraceabilityWithImageMismatch,
} from '../../utils/evidenceReviewDisplay';
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
  const { t } = useTranslation();
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
    <Box 
      sx={{ 
        p: 2, 
        borderRadius: 2, 
        bgcolor: 'background.default', 
        border: '1px solid', 
        borderColor: 'divider',
        display: 'flex',
        flexDirection: 'column',
        gap: 2.5
      }}
    >
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
            {t('results.summary_current_quantity')}
          </Typography>
          <Typography variant="h5" fontWeight={800} sx={{ lineHeight: 1, letterSpacing: -0.5 }}>
            {visibleQtyNum != null ? String(visibleQtyNum) : '—'}
          </Typography>
          {hasManualOverride && (
             <Typography variant="caption" color="primary.main" sx={{ fontWeight: 700, mt: 0.5, display: 'block', fontSize: '0.7rem' }}>
               {t('results.summary_manual_override')}
             </Typography>
          )}
        </Box>
        
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
            {t('results.summary_position_code')}
          </Typography>
          <Typography variant="body1" fontWeight={700}>
            {result.positionCode != null && result.positionCode.trim() !== '' ? result.positionCode : '—'}
          </Typography>
        </Box>

        {hasManualOverride && systemQtyNum != null && (
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
              {t('results.summary_system_original')}
            </Typography>
            <Typography variant="body1" fontWeight={600}>{String(systemQtyNum)}</Typography>
          </Box>
        )}

        <Box sx={{ gridColumn: hasManualOverride ? undefined : 'span 1' }}>
           <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
            {t('results.summary_count_origin')}
          </Typography>
          <Typography variant="body2" fontWeight={600} color="text.primary">
            {getCountOriginLabel(result)}
          </Typography>
        </Box>

        <Box>
           <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
            {t('results.summary_last_update')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
            {formatDate(result.updatedAt)}
          </Typography>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <StatusChip
          label={getReviewStatusLabelForDisplay(result.reviewStatus)}
          color={getReviewStatusColorForDisplay(result.reviewStatus)}
          size="small"
          variant="filled"
        />
        {shouldReplaceTraceabilityWithImageMismatch(result.reviewStatus) ? (
          <StatusChip
            label={getImageMismatchEvidenceLabel(true)}
            color="warning"
            size="small"
            variant="outlined"
          />
        ) : (
          <TraceabilityChip
            status={visibleTraceabilityToApiStatus(result.traceabilityStatus)}
            size="small"
          />
        )}
        <StatusChip
          label={t('results.summary_confidence_value', { value: confidenceStr })}
          variant="outlined"
          size="small"
        />
      </Box>
    </Box>
  );
}
