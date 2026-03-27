/**
 * Empty state — Re diseño 3.3 §8.9, §14.2: clear message, brief explanation, optional primary CTA.
 */

import type { ReactNode } from 'react';
import { Box, Paper, Typography } from '@mui/material';

export interface EmptyStateProps {
  /** Short headline (e.g. "No inventories yet"). */
  title?: string;
  /** Supporting copy. */
  message: string;
  /** Primary action (e.g. Create inventory). */
  action?: ReactNode;
  /** Paper padding (theme spacing units). Default 3. */
  padding?: number;
}

export default function EmptyState({ title, message, action, padding = 3 }: EmptyStateProps) {
  return (
    <Paper sx={{ p: padding, textAlign: 'center' }} variant="outlined">
      <Box sx={{ maxWidth: 480, mx: 'auto' }}>
        {title ? (
          <Typography variant="subtitle1" component="h2" fontWeight={600} gutterBottom>
            {title}
          </Typography>
        ) : null}
        <Typography color="text.secondary" variant="body2" paragraph={Boolean(title)} sx={{ mb: action ? 2 : 0 }}>
          {message}
        </Typography>
        {action ? <Box sx={{ display: 'flex', justifyContent: 'center' }}>{action}</Box> : null}
      </Box>
    </Paper>
  );
}
