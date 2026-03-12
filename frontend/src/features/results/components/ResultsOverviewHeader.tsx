/**
 * Epic 3 — Results overview page header.
 */

import { Button, Typography, Box } from '@mui/material';

export interface ResultsOverviewHeaderProps {
  title?: string;
  /** Optional context line (e.g. aisle code or job id). */
  context?: string;
  onBack?: () => void;
  backLabel?: string;
}

export default function ResultsOverviewHeader({
  title = 'Results',
  context,
  onBack,
  backLabel = 'Back to inventory',
}: ResultsOverviewHeaderProps) {
  return (
    <Box sx={{ mb: 3 }}>
      {onBack && (
        <Button sx={{ mb: 1.5 }} onClick={onBack}>
          ← {backLabel}
        </Button>
      )}
      <Typography variant="h5" component="h1">
        {title}
      </Typography>
      {context && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {context}
        </Typography>
      )}
    </Box>
  );
}
