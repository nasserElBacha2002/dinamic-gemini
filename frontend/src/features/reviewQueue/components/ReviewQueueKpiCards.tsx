/**
 * Sprint 4.2 — Review Queue KPI band (five workload signals).
 */

import { Box } from '@mui/material';
import { KpiCard } from '../../../components/ui';
import type { ReviewQueueSummary } from '../../../api/types';

export interface ReviewQueueKpiCardsProps {
  summary: ReviewQueueSummary;
}

export default function ReviewQueueKpiCards({ summary }: ReviewQueueKpiCardsProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: { xs: 'wrap', md: 'nowrap' },
        gap: 1.5,
        overflowX: { xs: 'visible', md: 'auto' },
        width: '100%',
        minWidth: 0,
        mb: 2,
        alignItems: 'stretch',
      }}
    >
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="Pending review" value={summary.pending_review} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="Low confidence" value={summary.low_confidence} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 160px', md: '0 0 160px' } }}>
        <KpiCard label="Invalid traceability" value={summary.invalid_traceability} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 130px', md: '0 0 130px' } }}>
        <KpiCard label="Qty zero" value={summary.qty_zero} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 150px', md: '0 0 150px' } }}>
        <KpiCard label="Missing evidence" value={summary.missing_evidence} />
      </Box>
    </Box>
  );
}
