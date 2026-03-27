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
  'delete_position',
] as const;
export type ReviewActionType = (typeof REVIEW_ACTION_TYPES)[number];

/** Epic 3.1.B — Traceability status values from backend (GET /jobs/{job_id}/entities, position summary).
 * Use this type for API params, response fields, and legacy entity/position views.
 * For the visible Result model (uppercase), use features/results types. */
export const TRACEABILITY_STATUSES = ['valid', 'missing', 'invalid', 'unvalidated'] as const;
export type ApiTraceabilityStatus = (typeof TRACEABILITY_STATUSES)[number];
