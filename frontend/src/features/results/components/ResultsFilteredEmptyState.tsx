/**
 * Epic 3 — Empty state when filters return no results.
 */

import { Paper, Typography, Button } from '@mui/material';

export interface ResultsFilteredEmptyStateProps {
  onClearFilter?: () => void;
}

export default function ResultsFilteredEmptyState({
  onClearFilter,
}: ResultsFilteredEmptyStateProps) {
  return (
    <Paper sx={{ p: 4, textAlign: 'center' }}>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        No results match the current filter.
      </Typography>
      {onClearFilter && (
        <Button variant="outlined" size="small" onClick={onClearFilter}>
          Clear filter
        </Button>
      )}
    </Paper>
  );
}
