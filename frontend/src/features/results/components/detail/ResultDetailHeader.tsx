/**
 * Epic 4 — Result Detail page header.
 */

import { Button, Typography, Box } from '@mui/material';

export interface ResultDetailHeaderProps {
  title?: string;
  context?: string;
  onBack?: () => void;
  backLabel?: string;
}

export default function ResultDetailHeader({
  title = 'Result',
  context,
  onBack,
  backLabel = 'Back to results',
}: ResultDetailHeaderProps) {
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
