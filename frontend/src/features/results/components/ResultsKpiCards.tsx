/**
 * Sprint 4.1 — Aisle Results KPI band (six workload summaries only).
 */

import { useTranslation } from 'react-i18next';
import { Box } from '@mui/material';
import { KpiCard, KpiCardBand } from '../../../components/ui';
import type { ResultsKpi } from '../selectors/resultsKpi';

export interface ResultsKpiCardsProps {
  kpi: ResultsKpi;
}

export default function ResultsKpiCards({ kpi }: ResultsKpiCardsProps) {
  const { t } = useTranslation();
  return (
    <KpiCardBand variant="flexStrip">
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label={t('results.kpi_total')} value={kpi.total} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label={t('results.kpi_needs_review')} value={kpi.needsReview} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label={t('results.kpi_low_confidence')} value={kpi.lowConfidence} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 160px' } }}>
        <KpiCard label={t('results.kpi_invalid_traceability')} value={kpi.invalidTraceability} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label={t('results.kpi_qty_zero')} value={kpi.qtyZero} />
      </Box>
      <Box sx={{ flex: { xs: '1 1 140px', md: '0 0 140px' } }}>
        <KpiCard label={t('results.kpi_with_evidence')} value={kpi.withEvidence} />
      </Box>
    </KpiCardBand>
  );
}
