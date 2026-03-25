/**
 * Epic 5 — Navigation context for Result Detail previous/next.
 * Used when navigating from Results overview so detail can show sequential controls.
 */

import type { ResultsFilterKind } from '../selectors';

const VALID_FILTERS: ResultsFilterKind[] = [
  'all',
  'needs_review',
  'low_confidence',
  'qty_zero',
  'invalid_traceability',
  'missing_evidence',
];

function isResultsFilterKind(value: unknown): value is ResultsFilterKind {
  return typeof value === 'string' && VALID_FILTERS.includes(value as ResultsFilterKind);
}

/** Where the user should return when leaving detail (drives breadcrumbs + back). */
export type ResultDetailReturnTo = 'aisle_results' | 'review_queue';

/** State passed via React Router location.state when opening Result Detail from the list. */
export interface ResultDetailNavigationState {
  resultIds: string[];
  filter?: ResultsFilterKind;
  /** When omitted, treated as aisle flow (backward compatible). */
  returnTo?: ResultDetailReturnTo;
}

export interface ResultNavigationContext {
  currentIndex: number;
  previousId: string | null;
  nextId: string | null;
  total: number;
}

/**
 * Parse and validate navigation state from location.state.
 * Returns null when state is missing, malformed, or resultIds is not a non-empty array of strings.
 * Used so the detail page degrades gracefully (no prev/next) instead of trusting a raw cast.
 */
export function parseResultDetailNavigationState(
  state: unknown
): ResultDetailNavigationState | null {
  if (state == null || typeof state !== 'object') return null;
  const o = state as Record<string, unknown>;
  const resultIds = o.resultIds;
  if (!Array.isArray(resultIds) || resultIds.length === 0) return null;
  const ids: string[] = [];
  for (const id of resultIds) {
    if (typeof id !== 'string' || id.trim() === '') return null;
    ids.push(id.trim());
  }
  const filter = o.filter;
  const filterOk =
    filter === undefined ||
    filter === null ||
    isResultsFilterKind(filter);
  if (!filterOk) return null;
  const rawReturn = o.returnTo;
  const returnTo =
    rawReturn === 'review_queue' || rawReturn === 'aisle_results'
      ? (rawReturn as ResultDetailReturnTo)
      : undefined;
  return {
    resultIds: ids,
    filter: filter === undefined || filter === null ? undefined : (filter as ResultsFilterKind),
    returnTo,
  };
}

/**
 * Safe read of filter from location.state when returning from Result Detail.
 * Detail passes { filter } on back navigation. Returns 'all' if state is missing or invalid.
 */
export function getInitialFilterFromReturnState(state: unknown): ResultsFilterKind {
  if (state == null || typeof state !== 'object') return 'all';
  const o = state as Record<string, unknown>;
  return isResultsFilterKind(o.filter) ? o.filter : 'all';
}

/**
 * Compute previous/next from the current visible result set.
 * Returns null if currentId is not in the list or list is empty.
 */
export function getResultNavigationContext(
  resultIds: string[],
  currentId: string
): ResultNavigationContext | null {
  if (!resultIds.length || !currentId) return null;
  const currentIndex = resultIds.indexOf(currentId);
  if (currentIndex < 0) return null;

  return {
    currentIndex,
    previousId: currentIndex > 0 ? resultIds[currentIndex - 1]! : null,
    nextId:
      currentIndex < resultIds.length - 1 ? resultIds[currentIndex + 1]! : null,
    total: resultIds.length,
  };
}
