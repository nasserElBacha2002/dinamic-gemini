/**
 * Layout widths and responsive tokens — Re diseño 3.3 §7.2 + mobile-first shell.
 *
 * **Breakpoint mapping (MUI defaults preserved to avoid mass sx regressions):**
 * | Product label | MUI key | Width (px) | Nav / tables |
 * |---------------|---------|------------|--------------|
 * | Mobile        | xs–sm   | 0–899      | Temporary nav; compact / card views |
 * | Tablet+       | md+     | ≥900       | Permanent nav; full tables |
 *
 * Prefer `useAppBreakpoint()` over ad-hoc `useMediaQuery` for shell and DataTable.
 */

export const MAIN_CONTENT_MAX_WIDTH_PX = 1400;

/**
 * Max width for focused review/detail columns inside `AppMain` (Re diseño 3.3 §9.9).
 */
export const DETAIL_COLUMN_MAX_WIDTH_PX = 700;

/** Permanent / temporary nav drawer width (desktop and mobile overlay). */
export const DRAWER_WIDTH_PX = 260;

/** Minimum interactive target size (approx. WCAG / Apple HIG). */
export const TOUCH_TARGET_MIN_PX = 44;

/** AppBar / toolbar height tokens. */
export const APP_BAR_HEIGHT_XS_PX = 56;
export const APP_BAR_HEIGHT_SM_PX = 64;

/**
 * Safe-area insets for notched devices. Apply on shell chrome (AppBar, drawers, dialogs).
 */
export const SAFE_AREA = {
  top: 'env(safe-area-inset-top, 0px)',
  right: 'env(safe-area-inset-right, 0px)',
  bottom: 'env(safe-area-inset-bottom, 0px)',
  left: 'env(safe-area-inset-left, 0px)',
} as const;

/** Dynamic viewport height (avoids iOS 100vh toolbar issues). */
export const VIEWPORT_MIN_HEIGHT = '100dvh';

/**
 * MUI breakpoint key at which the shell switches from temporary to permanent nav,
 * and DataTable prefers the desktop table over mobile cards (when `renderMobileItem` is set).
 */
export const SHELL_PERMANENT_NAV_BREAKPOINT = 'md' as const;
