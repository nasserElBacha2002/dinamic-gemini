import type { ReactNode } from 'react';
import { Box } from '@mui/material';
import { MAIN_CONTENT_MAX_WIDTH_PX, SAFE_AREA } from './layoutConstants';

export interface AppMainProps {
  children: ReactNode;
}

/**
 * Main content column inside the authenticated shell (Re diseño 3.3 §4.1, §7.2).
 * Default is **wide** for lists and operational tables. Detail/review columns apply `maxWidth` inside this container
 * (see `DETAIL_COLUMN_MAX_WIDTH_PX`), not by adding a second shell.
 */
export default function AppMain({ children }: AppMainProps) {
  return (
    <Box
      component="main"
      sx={{
        flex: 1,
        minWidth: 0,
        maxWidth: `min(100%, ${MAIN_CONTENT_MAX_WIDTH_PX}px)`,
        width: '100%',
        p: { xs: 1.5, sm: 2, md: 3 },
        pl: { xs: `max(${SAFE_AREA.left}, 12px)`, sm: 2, md: 3 },
        pr: { xs: `max(${SAFE_AREA.right}, 12px)`, sm: 2, md: 3 },
        mx: 'auto',
        boxSizing: 'border-box',
        overflowX: 'clip',
      }}
    >
      {children}
    </Box>
  );
}
