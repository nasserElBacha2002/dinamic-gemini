/**
 * Named aliases for page-level rows. Source of truth for field shapes is `api/types` (wire DTOs).
 */

import type { InventoryListItem } from '../api/types';

/** Row type for the inventories table; each element of ``items`` on GET /api/v3/inventories (not GET-by-id / create). */
export type InventoriesListRow = InventoryListItem;
