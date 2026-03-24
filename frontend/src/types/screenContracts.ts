/**
 * Screen-oriented data shapes (product list/detail), aligned with Sprint 1.2+ API contracts.
 * Wire DTOs live in api/types; this module documents how list/detail pages should consume them.
 */

import type { InventoryListItem } from '../api/types';

/** Inventories list page: table rows come from GET /api/v3/inventories (InventoryListItem). */
export type InventoriesListRow = InventoryListItem;
