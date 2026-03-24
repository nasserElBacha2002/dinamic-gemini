/**
 * Review / quality thresholds shared by the Results feature and status alignment.
 * Single source — avoids drift between filters, KPIs, and plan-aligned helpers.
 */

/** Confidence strictly below this is treated as "low confidence" for KPIs, filters, and alignment. */
export const LOW_CONFIDENCE_THRESHOLD = 0.5;
