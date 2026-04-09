/**
 * Epic 4 — Empty / not-found state for Result Detail.
 */

import { Paper, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface ResultDetailEmptyStateProps {
  message?: string;
}

export default function ResultDetailEmptyState({ message }: ResultDetailEmptyStateProps) {
  const { t } = useTranslation();
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message ?? t('review.result_not_found')}</Typography>
    </Paper>
  );
}
