/**
 * Target taxonomies from docs/Plan implementacion 3.3.md and docs/Re diseño 3.3.md (Sprint 1.1 / §11).
 * Current API values live in api/types/shared.ts.
 * Mappings from API → these targets: statusAlignment.ts (+ docs/Stage1_status_contract_alignment.md).
 *
 * Quality is not a single exclusive enum: traceability and low-confidence are separate dimensions
 * (see deriveQualityAlignmentSignals in statusAlignment.ts).
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
  'image_mismatch',
  'deleted',
] as const;
export type TargetResultReviewStatus = (typeof TARGET_RESULT_REVIEW_STATUSES)[number];

/**
 * Traceability-only labels for the product plan (§11 quality axis).
 * Independent of the low-confidence signal (confidence vs threshold).
 */
export const TRACEABILITY_PLAN_LABELS = ['valid_traceability', 'invalid_traceability'] as const;
export type TraceabilityPlanLabel = (typeof TRACEABILITY_PLAN_LABELS)[number];
