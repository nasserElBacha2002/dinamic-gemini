/**
 * Shared status enums and consts — used by API DTOs and UI.
 * Single source of truth for backend-aligned status values.
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
export const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const;
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
