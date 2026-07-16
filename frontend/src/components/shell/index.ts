/**
 * Shell primitives for authenticated layout (Sprint 2.1 foundation).
 *
 * **Header model:** `AppShell` topbar = route screen identity (Re diseño 3.3 §4.3). `PageHeader` = breadcrumbs,
 * entity title when needed, subtitle, actions in the main column (§8.2). See `PageHeader.tsx` and `layout/AppShell.tsx`.
 */

export { default as PageHeader } from './PageHeader';
export type { PageHeaderProps, PageHeaderBreadcrumb, PageHeaderOverflowAction } from './PageHeader';
export { default as AppMain } from './AppMain';
export type { AppMainProps } from './AppMain';
export { default as UserMenu } from './UserMenu';
export {
  MAIN_CONTENT_MAX_WIDTH_PX,
  DETAIL_COLUMN_MAX_WIDTH_PX,
  DRAWER_WIDTH_PX,
  TOUCH_TARGET_MIN_PX,
  SAFE_AREA,
  VIEWPORT_MIN_HEIGHT,
  SHELL_PERMANENT_NAV_BREAKPOINT,
} from './layoutConstants';
