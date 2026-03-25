/**
 * Sprint 4.1 — Aisle Results KPI band (six workload summaries only).
 */

import { Box } from '@mui/material';
import { KpiCard } from '../../../components/ui';
import type { ResultsKpi } from '../selectors/resultsKpi';

export interface ResultsKpiCardsProps {
  kpi: ResultsKpi;
}

export default function ResultsKpiCards({ kpi }: ResultsKpiCardsProps) {
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
        <KpiCard label="Total results" value={kpi.total} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="Needs review" value={kpi.needsReview} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="Low confidence" value={kpi.lowConfidence} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 160px' } }}>
        <KpiCard label="Invalid traceability" value={kpi.invalidTraceability} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="Qty zero" value={kpi.qtyZero} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label="With evidence" value={kpi.withEvidence} />
      </Box>
    </Box>
  );
}
