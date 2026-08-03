/**
 * Aisle locations (physical positioning) + positioning labels — Phase 1 wire types.
 * Distinct from CV “positions” (detected product review units).
 */

export const AISLE_LOCATION_STATUSES = ['ACTIVE', 'INACTIVE'] as const;
export type AisleLocationStatus = (typeof AISLE_LOCATION_STATUSES)[number];

export const AISLE_LOCATION_LABEL_STATUSES = [
  'ACTIVE',
  'REPLACED',
  'INVALIDATED',
  'ARCHIVED',
] as const;
export type AisleLocationLabelStatus = (typeof AISLE_LOCATION_LABEL_STATUSES)[number];

export interface AisleLocation {
  id: string;
  client_id: string;
  aisle_id: string;
  code: string;
  normalized_code: string;
  status: AisleLocationStatus | string;
  created_at: string;
  updated_at: string;
  display_name?: string | null;
  description?: string | null;
  created_by?: string | null;
  public_identifier?: string;
}

export interface AisleLocationListResponse {
  items: AisleLocation[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface CreateAisleLocationRequest {
  code: string;
  display_name?: string | null;
  description?: string | null;
}

export interface UpdateAisleLocationRequest {
  display_name?: string | null;
  description?: string | null;
  status?: AisleLocationStatus | null;
}

/** DINAMIC_POSITION payload (Phase 1 — no item/SKU fields). */
export interface PositioningLabelPayload {
  type: string;
  version: number;
  label_id: string;
  position_id: string;
  [key: string]: unknown;
}

export interface AisleLocationLabel {
  id: string;
  client_id: string;
  location_id: string;
  public_identifier: string;
  payload_version: number;
  marker_version: number;
  template_version: number;
  status: AisleLocationLabelStatus | string;
  payload: PositioningLabelPayload | Record<string, unknown>;
  generated_at: string;
  payload_hash?: string | null;
  signature_status: string;
  generated_by?: string | null;
  invalidated_at?: string | null;
  invalidation_reason?: string | null;
  replaced_by_label_id?: string | null;
  replaced_at?: string | null;
}

export interface AisleLocationLabelListResponse {
  items: AisleLocationLabel[];
}

export interface IssueAisleLocationLabelRequest {
  idempotency_key?: string | null;
}

export interface InvalidateAisleLocationLabelRequest {
  reason?: string | null;
}
