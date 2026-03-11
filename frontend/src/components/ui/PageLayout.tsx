/**
 * Shared page container: padding, max-width, centered.
 * Use for all list/detail screens to keep layout consistent.
 */

import { Box, type SxProps, type Theme } from '@mui/material';

export interface PageLayoutProps {
  children: React.ReactNode;
  /** Max width in px. Default 900. */
  maxWidth?: number;
  sx?: SxProps<Theme>;
}

export default function PageLayout({ children, maxWidth = 900, sx }: PageLayoutProps) {
  return (
    <Box sx={{ p: 3, maxWidth, mx: 'auto', ...sx }}>
      {children}
    </Box>
  );
}
