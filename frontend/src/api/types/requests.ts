/**
 * API request DTOs — request body contracts sent to the backend.
 */

import type { ReviewActionType } from './shared';

export interface CreateInventoryRequest {
  name: string;
}

export interface CreateAisleRequest {
  code: string;
}

/** Request body for POST .../positions/{position_id}/reviews. */
export interface ReviewActionRequest {
  action_type: ReviewActionType;
  product_id?: string | null;
  corrected_quantity?: number | null;
  sku?: string | null;
  description?: string | null;
  position_code?: string | null;
}
