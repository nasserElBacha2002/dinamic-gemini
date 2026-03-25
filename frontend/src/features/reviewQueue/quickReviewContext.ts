/**
 * Sprint 4.4 — Shared context for Quick Review (queue row or aisle row).
 */

import type { PositionSummary, ReviewQueueItem } from '../../api/types';

export interface QuickReviewContext {
  inventoryId: string;
  inventoryName: string;
  aisleCode: string;
  aisleId: string;
  position: PositionSummary;
}

export function reviewQueueItemToContext(row: ReviewQueueItem): QuickReviewContext {
  return {
    inventoryId: row.inventory_id,
    inventoryName: row.inventory_name,
    aisleCode: row.aisle_code,
    aisleId: row.position.aisle_id,
    position: row.position,
  };
}
