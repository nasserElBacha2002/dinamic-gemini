/**
 * Sprint 4.1 — Explainable review priority for Aisle Results (client-side ordering only).
 *
 * Tiers (lower sortOrder = review sooner):
 * - P1: needs review AND (invalid traceability OR missing evidence)
 * - P2: needs review AND (low confidence OR qty zero)
 * - P3: needs review only
 * - P4: everything else
 */

import type { ResultSummary } from '../types';
import { LOW_CONFIDENCE_THRESHOLD } from '../constants';

export type ResultPriorityTier = 1 | 2 | 3 | 4;

export interface ResultPriority {
  tier: ResultPriorityTier;
  /** Stable sort key (asc = higher priority first). */
  sortOrder: number;
  label: string;
}

function displayQtyZero(r: ResultSummary): boolean {
  const q = r.resolvedQty ?? r.detectedQty;
  return q === 0;
}

function lowConfidence(r: ResultSummary): boolean {
  return r.confidence != null && r.confidence < LOW_CONFIDENCE_THRESHOLD;
}

/**
 * Derive priority from explicit flags only (no opaque scores).
 */
export function deriveResultPriority(r: ResultSummary): ResultPriority {
  const needs = r.needsReview;
  const invalidTrace = r.traceabilityStatus === 'INVALID';
  const missingEv = !r.hasEvidence;
  const qty0 = displayQtyZero(r);
  const lowConf = lowConfidence(r);

  if (needs && (invalidTrace || missingEv)) {
    return { tier: 1, sortOrder: 0, label: 'P1' };
  }
  if (needs && (lowConf || qty0)) {
    return { tier: 2, sortOrder: 1, label: 'P2' };
  }
  if (needs) {
    return { tier: 3, sortOrder: 2, label: 'P3' };
  }
  return { tier: 4, sortOrder: 3, label: 'P4' };
}

export function sortResultsByPriority(results: ResultSummary[]): ResultSummary[] {
  return [...results].sort((a, b) => {
    const pa = deriveResultPriority(a);
    const pb = deriveResultPriority(b);
    if (pa.sortOrder !== pb.sortOrder) return pa.sortOrder - pb.sortOrder;
    const skuA = (a.sku ?? '').toLowerCase();
    const skuB = (b.sku ?? '').toLowerCase();
    if (skuA !== skuB) return skuA.localeCompare(skuB);
    return a.id.localeCompare(b.id);
  });
}
