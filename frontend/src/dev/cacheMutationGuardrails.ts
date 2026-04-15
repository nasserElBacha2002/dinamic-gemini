/**
 * Phase 9 — development guardrails on top of Phase 8 observability events.
 * Warns on suspicious patterns; does not throw. Off in Vitest unless explicitly enabled for tests.
 *
 * Intentionally does not import `cacheMutationObservability` (avoid circular ESM with pushEvent).
 */

let guardrailsTestOverride: boolean | null = null;

/** Structural slice of observability rows (keep aligned with `CacheMutationObservabilityEvent`). */
export type CacheObsRow = { kind: string; at: number } & Record<string, unknown>;

/** For unit tests only — `null` restores default rules. */
export function setCacheMutationGuardrailsTestOverride(value: boolean | null): void {
  guardrailsTestOverride = value;
}

function readLocalStorage(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function isCacheMutationGuardrailsActive(): boolean {
  if (guardrailsTestOverride !== null) return guardrailsTestOverride;
  if (typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test') return false;
  if (typeof import.meta !== 'undefined' && !import.meta.env?.DEV) {
    return readLocalStorage('dinamic:cacheGuardrails') === '1';
  }
  if (readLocalStorage('dinamic:cacheGuardrails') === '0') return false;
  return true;
}

const warnedKeys = new Set<string>();

function warnOnce(key: string, message: string, detail: unknown): void {
  if (!isCacheMutationGuardrailsActive()) return;
  if (warnedKeys.has(key)) return;
  warnedKeys.add(key);
  // eslint-disable-next-line no-console -- Phase 9 dev diagnostics
  console.warn(`[dinamic:cache-guard] ${message}`, detail);
}

/**
 * Pure helper — used by tests to assert guardrail logic without console.
 * Pass recent events newest-last (same order as observability buffer).
 */
export function computeGuardrailNotices(recent: ReadonlyArray<CacheObsRow>): string[] {
  const notices: string[] = [];
  const last = recent[recent.length - 1];
  if (!last) return notices;

  if (last.kind === 'review_action_cache') {
    if (last.strategy === 'default') {
      notices.push('review_action_used_default_strategy');
    }
    const fallbacks = last.fallbackInvalidations as string[] | undefined;
    const patchHits = last.patchHits as string[] | undefined;
    if (last.strategy === 'reviewQueue' && Array.isArray(fallbacks) && fallbacks.length >= 2) {
      notices.push('review_queue_multiple_fallbacks');
    }
    if (
      last.strategy === 'aisleResults' &&
      Array.isArray(patchHits) &&
      patchHits.length === 0 &&
      Array.isArray(fallbacks) &&
      fallbacks.length >= 2
    ) {
      notices.push('aisle_results_cold_cache_heavy_fallback');
    }
  }

  if (last.kind === 'mutation_invalidations') {
    const labels = last.labels as string[] | undefined;
    if (Array.isArray(labels) && labels.length > 6) {
      notices.push('mutation_high_invalidation_fanout');
    }
  }

  if (last.kind === 'explicit_refresh') {
    const lastKs = last.keySummary as string;
    const lastAt = last.at as number;
    const dup = recent.filter((e) => {
      if (e.kind !== 'explicit_refresh') return false;
      if (e.flow !== last.flow) return false;
      if ((e as { keySummary?: string }).keySummary !== lastKs) return false;
      return lastAt - (e.at as number) <= 2000;
    });
    if (dup.length >= 2) {
      notices.push('duplicate_explicit_refresh_same_key');
    }
  }

  return notices;
}

/** Call after each observability push (dev / optional staging). */
export function reportGuardrailsForNewEvent(row: CacheObsRow, buffer: ReadonlyArray<CacheObsRow>): void {
  if (!isCacheMutationGuardrailsActive()) return;
  const notices = computeGuardrailNotices(buffer);
  for (const n of notices) {
    if (n === 'review_action_used_default_strategy') {
      warnOnce(
        'default-strategy',
        'Review action ran with default (broad) invalidation — pass strategy from QuickReviewDrawer when context is known.',
        row
      );
    }
    if (n === 'review_queue_multiple_fallbacks') {
      warnOnce('rq-fallback2', 'Review queue strategy hit multiple fallbacks — cold cache or missing row?', row);
    }
    if (n === 'aisle_results_cold_cache_heavy_fallback') {
      warnOnce(
        'aisle-cold',
        'Aisle results strategy had no patch hits but multiple fallbacks — expect extra refetch traffic.',
        row
      );
    }
    if (n === 'mutation_high_invalidation_fanout') {
      warnOnce('fanout-' + row.at, 'Mutation listed many invalidation domains — confirm each is required.', row);
    }
    if (n === 'duplicate_explicit_refresh_same_key') {
      const ks = String((row as { keySummary?: string }).keySummary ?? '');
      warnOnce('dup-refresh-' + ks, 'Duplicate explicit_refresh for same key within 2s.', row);
    }
  }
}
