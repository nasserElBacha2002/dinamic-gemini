/**
 * Epic 5 — Previous/next navigation and position indicator for Result Detail.
 */

import { Box, Button, Typography } from '@mui/material';
import type { ResultNavigationContext } from '../../utils/navigationContext';

export interface ResultDetailNavigationProps {
  context: ResultNavigationContext;
  onNavigate: (resultId: string) => void;
  disabled?: boolean;
}

export default function ResultDetailNavigation({
  context,
  onNavigate,
  disabled,
}: ResultDetailNavigationProps) {
  const { currentIndex, previousId, nextId, total } = context;
  const oneBased = currentIndex + 1;

  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 1.5,
        mb: 2,
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ mr: 0.5 }}>
        Result {oneBased} of {total}
      </Typography>
      <Button
        size="small"
        variant="outlined"
        disabled={disabled || !previousId}
        onClick={() => previousId && !disabled && onNavigate(previousId)}
        aria-label="Previous result"
      >
        ← Previous
      </Button>
      <Button
        size="small"
        variant="outlined"
        disabled={disabled || !nextId}
        onClick={() => nextId && !disabled && onNavigate(nextId)}
        aria-label="Next result"
      >
        Next →
      </Button>
    </Box>
  );
}
