/**
 * Sprint 5.3 — shared operator-facing copy for consistent terminology across screens.
 * Prefer importing from here when multiple pages need the same headline or empty-state text.
 */

/** Default table body when `DataTable` has no custom `emptyState`. */
export const TABLE_EMPTY_DEFAULT = 'No results to display.';

export const inventoryListEmpty = {
  title: 'No inventories yet',
  /** Single phrasing used on list + dashboard recent table. */
  message: 'Create an inventory to add aisles, run processing, and complete review.',
} as const;

export const dashboardPlaceholder = {
  attention:
    'Inventories and aisles that need attention will appear here when the dashboard summary API is available.',
  activity:
    'Recent uploads, processing, and review actions will appear here when the activity feed API is available.',
  kpiFootnote: 'Values will appear when the dashboard summary API is available.',
} as const;

export const recentInventoriesCaption = 'Showing the 10 most recently active inventories.';
