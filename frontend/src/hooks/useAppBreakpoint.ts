/**
 * Centralized viewport classification for shell, tables, and overlays.
 * Uses MUI `useMediaQuery` + theme breakpoints (no `window.innerWidth`).
 *
 * Mapping (see `layoutConstants.ts`):
 * - `isMobile` / `!isMdUp`: temporary nav, compact layouts, DataTable cards when provided
 * - `isMdUp`: permanent nav, full tables
 */

import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { SHELL_PERMANENT_NAV_BREAKPOINT } from '../components/shell/layoutConstants';

export interface AppBreakpoint {
  /** True when viewport ≥ theme `md` (900px with default MUI values). */
  isMdUp: boolean;
  /** True when viewport ≥ theme `sm` (600px). */
  isSmUp: boolean;
  /** True when viewport &lt; `md` — temporary nav + compact views. */
  isMobileNav: boolean;
  /** Alias: compact / phone-oriented layouts (`!isMdUp`). */
  isCompact: boolean;
  /** Permanent sidebar + desktop tables. */
  isDesktopShell: boolean;
}

export function useAppBreakpoint(): AppBreakpoint {
  const theme = useTheme();
  const isMdUp = useMediaQuery(theme.breakpoints.up(SHELL_PERMANENT_NAV_BREAKPOINT));
  const isSmUp = useMediaQuery(theme.breakpoints.up('sm'));

  return {
    isMdUp,
    isSmUp,
    isMobileNav: !isMdUp,
    isCompact: !isMdUp,
    isDesktopShell: isMdUp,
  };
}
