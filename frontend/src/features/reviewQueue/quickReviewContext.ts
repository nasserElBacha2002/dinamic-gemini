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
  /** Resolved inventory job for position detail / evidence; must match visible aisle results slice. */
  jobId?: string | null;
  /**
   * Aisle review: fetch position detail without SKU-representative redirect so evidence matches the row.
   */
  exactPositionDetail?: boolean;
}

export function reviewQueueItemToContext(row: ReviewQueueItem, resultIds: string[]): QuickReviewContext {
  const jid = row.position.job_id?.trim();
  return {
    inventoryId: row.inventory_id,
    inventoryName: row.inventory_name,
    aisleCode: row.aisle_code,
    aisleId: row.position.aisle_id,
    positionId: row.position.id,
    resultIds,
    returnTo: 'review_queue',
    jobId: jid || undefined,
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
      /** From `position.job_id` when present — aligns queue review with the row's storage slice. */
      jobId?: string | null;
    }
  | {
      kind: 'aisle';
      positionId: string;
      resultIds: string[];
      filter?: ResultsFilterKind;
      /** Preserved when deep-linking into review with `?jobId=` on the positions route. */
      jobId?: string | null;
      exactPositionDetail?: boolean;
    };
