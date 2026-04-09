/**
 * Sprint 4.2 — Review Queue KPI band (five workload signals).
 */

import { useTranslation } from 'react-i18next';
import { Box } from '@mui/material';
import { KpiCard } from '../../../components/ui';
import type { ReviewQueueSummary } from '../../../api/types';

export interface ReviewQueueKpiCardsProps {
  summary: ReviewQueueSummary;
}

export default function ReviewQueueKpiCards({ summary }: ReviewQueueKpiCardsProps) {
  const { t } = useTranslation();
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: 'repeat(2, minmax(0, 1fr))',
          sm: 'repeat(3, minmax(0, 1fr))',
          md: 'repeat(5, minmax(0, 1fr))',
        },
        gap: 1.5,
        width: '100%',
        minWidth: 0,
        mb: 2,
        alignItems: 'stretch',
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <KpiCard label={t('results.kpi_needs_review')} value={summary.pending_review} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <KpiCard label={t('results.kpi_low_confidence')} value={summary.low_confidence} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <KpiCard label={t('results.kpi_invalid_traceability')} value={summary.invalid_traceability} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <KpiCard label={t('results.kpi_qty_zero')} value={summary.qty_zero} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <KpiCard label={t('results.kpi_missing_evidence')} value={summary.missing_evidence} />
      </Box>
    </Box>
  );
}
