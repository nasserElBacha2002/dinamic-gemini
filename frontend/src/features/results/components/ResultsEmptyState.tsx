/**
 * Epic 3 — Empty state for the Results overview (no results at all).
 */

import { useTranslation } from 'react-i18next';
import { Paper, Typography } from '@mui/material';

export interface ResultsEmptyStateProps {
  message?: string;
}

export default function ResultsEmptyState({ message }: ResultsEmptyStateProps) {
  const { t } = useTranslation();
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message ?? t('positions.empty_results')}</Typography>
    </Paper>
  );
}
