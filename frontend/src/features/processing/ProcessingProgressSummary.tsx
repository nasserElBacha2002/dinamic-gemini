import { useTranslation } from 'react-i18next';
import { Box, Paper, Typography } from '@mui/material';
import type { ProcessingJobProgressSummary } from '../../api/types/processing';

export interface ProcessingProgressSummaryProps {
  summary?: ProcessingJobProgressSummary | null;
}

export default function ProcessingProgressSummary({ summary }: ProcessingProgressSummaryProps) {
  const { t } = useTranslation();

  if (!summary) return null;

  const rows = [
    { label: t('processing.summary.total'), value: summary.total },
    { label: t('processing.summary.resolved'), value: summary.resolved },
    { label: t('processing.summary.failed'), value: summary.failed },
    { label: t('processing.summary.pending'), value: summary.pending },
    { label: t('processing.summary.processing'), value: summary.processing },
    { label: t('processing.summary.manualReview'), value: summary.manual_review },
  ];

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="processing-progress-summary">
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('processing.summary.title')}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 1 }}>
        {rows.map((row) => (
          <Box key={row.label}>
            <Typography variant="caption" color="text.secondary">
              {row.label}
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {row.value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}
