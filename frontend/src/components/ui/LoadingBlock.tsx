/**
 * Centered loading state: spinner with optional message.
 * Use for list/detail loading and inline section loading.
 */

import { Box, CircularProgress, Typography, type SxProps, type Theme } from '@mui/material';

export interface LoadingBlockProps {
  /** Optional short message next to spinner (e.g. "Loading metrics…"). */
  message?: string;
  /** Spinner size in px. Default 40. */
  size?: number;
  /** Vertical padding. Default 4. */
  py?: number;
  sx?: SxProps<Theme>;
}

export default function LoadingBlock({ message, size = 40, py = 4, sx }: LoadingBlockProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 1,
        py,
        ...sx,
      }}
    >
      <CircularProgress size={size} />
      {message && (
        <Typography variant="body2" color="text.secondary">
          {message}
        </Typography>
      )}
    </Box>
  );
}
