/**
 * Epic 3 — Empty state when filters return no results.
 */

import { useTranslation } from 'react-i18next';
import { Paper, Typography, Button } from '@mui/material';

export interface ResultsFilteredEmptyStateProps {
  onClearFilter?: () => void;
}

export default function ResultsFilteredEmptyState({
  onClearFilter,
}: ResultsFilteredEmptyStateProps) {
  const { t } = useTranslation();
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        {t('results.filtered_empty_message')}
      </Typography>
      {onClearFilter && (
        <Button variant="outlined" size="small" onClick={onClearFilter}>
          {t('results.clear_filter')}
        </Button>
      )}
    </Paper>
  );
}
