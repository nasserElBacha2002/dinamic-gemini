/**
 * Target taxonomies from docs/Plan implementacion 3.3.md and docs/Re diseño 3.3.md (Sprint 1.1 / §11).
 * Current API values live in api/types/shared.ts.
 * Mappings from API → these targets: statusAlignment.ts (+ docs/Stage1_status_contract_alignment.md).
 */

export const TARGET_INVENTORY_STATUSES = [
  'draft',
  'in_progress',
  'completed',
  'archived',
] as const;
export type TargetInventoryStatus = (typeof TARGET_INVENTORY_STATUSES)[number];

export const TARGET_AISLE_STATUSES = [
  'empty',
  'assets_uploaded',
  'processing',
  'processed',
  'error',
] as const;
export type TargetAisleStatus = (typeof TARGET_AISLE_STATUSES)[number];

export const TARGET_RESULT_REVIEW_STATUSES = [
  'pending_review',
  'confirmed',
  'corrected',
  'deleted',
] as const;
export type TargetResultReviewStatus = (typeof TARGET_RESULT_REVIEW_STATUSES)[number];

export const TARGET_QUALITY_STATUSES = [
  'valid_traceability',
  'invalid_traceability',
  'low_confidence',
] as const;
export type TargetQualityStatus = (typeof TARGET_QUALITY_STATUSES)[number];
