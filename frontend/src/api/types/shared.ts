/**
 * Shared status enums and consts — used by API DTOs and UI.
 * Single source of truth for **wire/API** values (matches backend domain enums).
 *
 * **Product plan** taxonomy (implementation docs) differs; map API → doc labels via
 * `src/types/statusAlignment.ts`.
 */

export const INVENTORY_STATUSES = [
  'draft',
  'processing',
  'in_review',
  'completed',
  'failed',
] as const;
export type InventoryStatus = (typeof INVENTORY_STATUSES)[number];

export const INVENTORY_PROCESSING_MODES = ['production', 'test'] as const;
export type InventoryProcessingMode = (typeof INVENTORY_PROCESSING_MODES)[number];

export const AISLE_STATUSES = [
  'created',
  'assets_uploaded',
  'queued',
  'processing',
  'processed',
  'in_review',
  'completed',
  'failed',
] as const;
export type AisleStatus = (typeof AISLE_STATUSES)[number];

/** Backend job status values (v3 API). */
export const JOB_STATUSES = [
  'queued',
  'starting',
  'running',
  'cancel_requested',
  'canceled',
  'timed_out',
  'succeeded',
  'failed',
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

/** Backend position status values (result model — Épica 6). */
export const POSITION_STATUSES = ['detected', 'reviewed', 'corrected', 'deleted'] as const;
export type PositionStatus = (typeof POSITION_STATUSES)[number];

/** Backend evidence type values (result model — Épica 6). */
export const EVIDENCE_TYPES = [
  'original_image',
  'video_frame',
  'position_crop',
  'product_crop',
  'label_crop',
  'annotated_image',
] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

/** Backend review action type values. */
export const REVIEW_ACTION_TYPES = [
  'confirm',
  'update_quantity',
  'update_sku',
  'update_position_code',
  'mark_unknown',
  'mark_image_mismatch',
  'delete_position',
] as const;
export type ReviewActionType = (typeof REVIEW_ACTION_TYPES)[number];

/** Named wire strings for POST .../reviews payloads — must match ``REVIEW_ACTION_TYPES``. */
export const REVIEW_ACTION_WIRE = {
  CONFIRM: 'confirm',
  UPDATE_QUANTITY: 'update_quantity',
  UPDATE_SKU: 'update_sku',
  UPDATE_POSITION_CODE: 'update_position_code',
  MARK_UNKNOWN: 'mark_unknown',
  MARK_IMAGE_MISMATCH: 'mark_image_mismatch',
  DELETE_POSITION: 'delete_position',
} as const satisfies Record<string, ReviewActionType>;

/** Epic 3.1.B — Traceability status values from backend (GET /jobs/{job_id}/entities, position summary).
 * Use this type for API params, response fields, and legacy entity/position views.
 * For the visible Result model (uppercase), use features/results types. */
export const TRACEABILITY_STATUSES = ['valid', 'missing', 'invalid', 'unvalidated'] as const;
export type ApiTraceabilityStatus = (typeof TRACEABILITY_STATUSES)[number];

/** Backend client status values (Phase A foundation). */
export const CLIENT_STATUSES = ['active', 'inactive'] as const;
export type ClientStatus = (typeof CLIENT_STATUSES)[number];

/** Backend client supplier status values (Phase A foundation). */
export const CLIENT_SUPPLIER_STATUSES = ['active', 'inactive'] as const;
export type ClientSupplierStatus = (typeof CLIENT_SUPPLIER_STATUSES)[number];
