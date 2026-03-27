/**
 * Canonical review drawer context — queue row, aisle row, or deep-link compat shell.
 */

import type { ReviewQueueItem } from '../../api/types';
import type { ResultsFilterKind } from '../results/selectors';
import type { ResultDetailReturnTo } from '../results/utils/navigationContext';

export interface QuickReviewContext {
  inventoryId: string;
  inventoryName: string;
  aisleCode: string;
  aisleId: string;
  positionId: string;
  resultIds: string[];
  returnTo: ResultDetailReturnTo;
  filter?: ResultsFilterKind;
}

export function reviewQueueItemToContext(row: ReviewQueueItem, resultIds: string[]): QuickReviewContext {
  return {
    inventoryId: row.inventory_id,
    inventoryName: row.inventory_name,
    aisleCode: row.aisle_code,
    aisleId: row.position.aisle_id,
    positionId: row.position.id,
    resultIds,
    returnTo: 'review_queue',
  };
}

/** Passed in router `location.state` after redirect from `/positions/:id` (single review entry point). */
export type OpenReviewDrawerPayload =
  | {
      kind: 'queue';
      inventoryId: string;
      aisleId: string;
      positionId: string;
      resultIds: string[];
      inventoryName: string;
      aisleCode: string;
    }
  | {
      kind: 'aisle';
      positionId: string;
      resultIds: string[];
      filter?: ResultsFilterKind;
    };
