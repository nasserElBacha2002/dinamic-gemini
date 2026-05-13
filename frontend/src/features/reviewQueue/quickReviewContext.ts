/**
 * Canonical review drawer context — aisle results list or deep-link compat shell.
 */

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
  /**
   * Query param for GET position detail / evidence (read path). Must not be used as POST /reviews
   * ``job_id`` — that value comes only from ``position.job_id`` on the loaded row.
   */
  jobId?: string | null;
  /**
   * Aisle review: fetch position detail without SKU-representative redirect so evidence matches the row.
   */
  exactPositionDetail?: boolean;
}

/** Passed in router `location.state` after redirect from `/positions/:id` (single review entry point). */
export type OpenReviewDrawerPayload = {
  kind: 'aisle';
  positionId: string;
  resultIds: string[];
  filter?: ResultsFilterKind;
  /** Preserved when deep-linking into review with `?jobId=` on the positions route. */
  jobId?: string | null;
  exactPositionDetail?: boolean;
};
