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
import {
  DATA_TABLE_DEFAULT_DESKTOP_BREAKPOINT,
  DIALOG_FULLSCREEN_BREAKPOINT,
  FILTER_DRAWER_BREAKPOINT,
  SHELL_PERMANENT_NAV_BREAKPOINT,
  WIZARD_VERTICAL_BREAKPOINT,
} from '../components/shell/layoutConstants';

export interface AppBreakpoint {
  /** Phone-class viewport (< sm). */
  isPhone: boolean;
  /** Tablet / compact operational viewport (sm to < md with current MUI defaults). */
  isTablet: boolean;
  /** Desktop-class viewport (>= md). */
  isDesktop: boolean;
  /** True when viewport ≥ theme `md` (900px with default MUI values). */
  isMdUp: boolean;
  /** True when viewport ≥ theme `sm` (600px). */
  isSmUp: boolean;
  /** True when viewport < shell breakpoint — temporary nav. */
  isMobileNav: boolean;
  /** Alias retained for older shared components; prefer semantic flags below. */
  isCompact: boolean;
  /** Permanent sidebar + desktop tables. */
  isDesktopShell: boolean;
  useTemporaryNavigation: boolean;
  useMobileTableCards: boolean;
  useFullscreenDialog: boolean;
  useMobileFilterDrawer: boolean;
  useVerticalWizard: boolean;
}

export function useAppBreakpoint(): AppBreakpoint {
  const theme = useTheme();
  const isMdUp = useMediaQuery(theme.breakpoints.up(SHELL_PERMANENT_NAV_BREAKPOINT));
  const isSmUp = useMediaQuery(theme.breakpoints.up('sm'));
  const isDataTableDesktop = useMediaQuery(theme.breakpoints.up(DATA_TABLE_DEFAULT_DESKTOP_BREAKPOINT));
  const isDialogDesktop = useMediaQuery(theme.breakpoints.up(DIALOG_FULLSCREEN_BREAKPOINT));
  const isFilterDesktop = useMediaQuery(theme.breakpoints.up(FILTER_DRAWER_BREAKPOINT));
  const isWizardDesktop = useMediaQuery(theme.breakpoints.up(WIZARD_VERTICAL_BREAKPOINT));
  const useTemporaryNavigation = !isMdUp;
  const useMobileTableCards = !isDataTableDesktop;
  const useFullscreenDialog = !isDialogDesktop;
  const useMobileFilterDrawer = !isFilterDesktop;
  const useVerticalWizard = !isWizardDesktop;

  return {
    isPhone: !isSmUp,
    isTablet: isSmUp && !isMdUp,
    isDesktop: isMdUp,
    isMdUp,
    isSmUp,
    isMobileNav: useTemporaryNavigation,
    isCompact: useMobileTableCards,
    isDesktopShell: isMdUp,
    useTemporaryNavigation,
    useMobileTableCards,
    useFullscreenDialog,
    useMobileFilterDrawer,
    useVerticalWizard,
  };
}
