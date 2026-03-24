import type { ReactNode } from 'react';
import { Box } from '@mui/material';

export interface AppMainProps {
  children: ReactNode;
}

/**
 * Main content column inside the authenticated shell — desktop-first width and padding (Re diseño 3.3 §4.1, §7.2).
 */
export default function AppMain({ children }: AppMainProps) {
  return (
    <Box
      component="main"
      sx={{
        flex: 1,
        minWidth: 0,
        p: { xs: 2, md: 3 },
        maxWidth: 1400,
        width: '100%',
        mx: 'auto',
      }}
    >
      {children}
    </Box>
  );
}
