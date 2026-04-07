/**
 * Sprint 5.3 — shared operator-facing copy for consistent terminology across screens.
 * Prefer importing from here when multiple pages need the same headline or empty-state text.
 *
 * **Layout / heading rule (refinement):**
 * - The shell **topbar** (`shellTopBarCopy`) carries the **visible** route title + short subtitle for wayfinding.
 * - **`PageHeader`** on top-level list/analytics routes uses **`a11yTitle` + `actions` only** (no duplicate visible
 *   title/subtitle). Entity/detail routes keep a visible **`PageHeader` title** (e.g. inventory name) plus breadcrumbs.
 *
 * **Action columns:** Use the header **“Actions”** for row-level upload/process/log menus (operator-standard).
 *
 * **Placeholders:** Use product-facing tone (“when this data is available”), not implementation (“API”, “contract”).
 */

/** Default table body when `DataTable` has no custom `emptyState`. */
export const TABLE_EMPTY_DEFAULT = 'No results to display.';

export const inventoryListEmpty = {
  title: 'No inventories yet',
  message: 'Create an inventory to add aisles, run processing, and complete review.',
} as const;
