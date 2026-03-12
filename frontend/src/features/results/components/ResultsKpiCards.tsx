/**
 * Epic 3 — KPI summary strip for the Results overview.
 */

import { Box } from '@mui/material';
import { StatCard } from '../../../components/ui';
import type { ResultsKpi } from '../selectors/resultsKpi';

export interface ResultsKpiCardsProps {
  kpi: ResultsKpi;
}

export default function ResultsKpiCards({ kpi }: ResultsKpiCardsProps) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
        gap: 2,
        mb: 3,
      }}
    >
      <StatCard label="Total" value={kpi.total} />
      <StatCard label="Needs review" value={kpi.needsReview} />
      <StatCard label="Valid traceability" value={kpi.validTraceability} />
      <StatCard label="Non-valid traceability" value={kpi.nonValidTraceability} />
      <StatCard label="Qty 0" value={kpi.qtyZero} />
      <StatCard label="With evidence" value={kpi.withEvidence} />
      <StatCard label="Low confidence" value={kpi.lowConfidence} />
    </Box>
  );
}
