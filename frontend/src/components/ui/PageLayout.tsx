/**
 * Shared page container: horizontal padding, max-width, centered content.
 *
 * @deprecated Not adopted by current pages (they compose `SectionCard`, toolbars, and route-level layout instead).
 * Export kept for compatibility; revisit removal or a pilot adoption in **F8** once layout strategy is explicit.
 */

import { Box, type SxProps, type Theme } from '@mui/material';

/** @deprecated Prefer explicit page composition until `PageLayout` is part of an agreed shell. */
export interface PageLayoutProps {
  children: React.ReactNode;
  /** Max width in px. Default 900. */
  maxWidth?: number;
  sx?: SxProps<Theme>;
}

/** @deprecated See module JSDoc. */
export default function PageLayout({ children, maxWidth = 900, sx }: PageLayoutProps) {
  return (
    <Box sx={{ p: 3, maxWidth, mx: 'auto', ...sx }}>
      {children}
    </Box>
  );
}
