/**
 * Phase 8 — lightweight dev observability for TanStack Query cache / invalidation / patching.
 * No production analytics; no vendor SDKs. When inactive, all record* calls are O(1) no-ops.
 */

import type { QueryKey } from '@tanstack/react-query';
import { reportGuardrailsForNewEvent } from './cacheMutationGuardrails';

const MAX_EVENTS = 80;

/** Mirrors `ReviewMutationStrategy` + orchestration default (avoid import cycle with review patch module). */
export type ReviewStrategyObs = 'reviewQueue' | 'aisleResults' | 'detail' | 'default';

/** Test-only override: `true` / `false` forces on/off; `null` uses normal rules. */
let testOverride: boolean | null = null;

export function setCacheMutationObservabilityTestOverride(value: boolean | null): void {
  testOverride = value;
}

function readLocalStorageFlag(key: string): boolean {
  try {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

/**
 * Active in Vite dev, or when `localStorage['dinamic:cacheObs'] === '1'`, or positive test override.
 * In Vitest (`import.meta.env.MODE === 'test'`), inactive unless `setCacheMutationObservabilityTestOverride(true)`
 * so suite noise and buffer leakage are avoided.
 */
export function isCacheMutationObservabilityActive(): boolean {
  if (testOverride !== null) return testOverride;
  if (typeof import.meta !== 'undefined' && import.meta.env?.MODE === 'test') return false;
  if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) return true;
  return readLocalStorageFlag('dinamic:cacheObs');
}

function isConsoleLoggingEnabled(): boolean {
  if (testOverride === true) return false;
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem('dinamic:cacheObs:console') === '0') {
      return false;
    }
  } catch {
    /* ignore */
  }
  return typeof import.meta !== 'undefined' && Boolean(import.meta.env?.DEV);
}

export type ReviewActionCacheObsEvent = {
  kind: 'review_action_cache';
  strategy: ReviewStrategyObs;
  scope: { inventoryId: string; aisleId: string; positionId: string };
  /** Where `setQueryData` / `removeQueries` satisfied the domain without invalidation. */
  patchHits: Array<'review_queue_list' | 'position_detail' | 'positions_list'>;
  /** `invalidateQueries` used because patch missed, no-op, or delete path. */
  fallbackInvalidations: string[];
  /** Invalidations that are intentional follow-ups (not “patch failed”), e.g. merge after aisle review. */
  directInvalidations: string[];
};

export type NonReviewPatchObsEvent = {
  kind: 'non_review_patch';
  flow: 'create_aisle' | 'promote_operational_job';
  inventoryId: string;
  aisleId?: string;
  patched: boolean;
  note?: string;
};

export type MutationInvalidationsObsEvent = {
  kind: 'mutation_invalidations';
  flow:
    | 'useCreateAisle'
    | 'useStartAisleProcessing'
    | 'useRunAisleMerge'
    | 'usePromoteAisleOperationalJob';
  labels: string[];
};

export type ExplicitRefreshObsEvent = {
  kind: 'explicit_refresh';
  flow: 'merge_merge_results';
  keySummary: string;
  mechanism: 'fetchQuery';
};

export type CacheMutationObservabilityEvent =
  | ReviewActionCacheObsEvent
  | NonReviewPatchObsEvent
  | MutationInvalidationsObsEvent
  | ExplicitRefreshObsEvent;

type Timestamped = CacheMutationObservabilityEvent & { at: number };

const buffer: Timestamped[] = [];

let windowHookInstalled = false;

function installWindowHook(): void {
  if (windowHookInstalled || typeof window === 'undefined') return;
  windowHookInstalled = true;
  (window as unknown as { __DINAMIC_CACHE_OBS__?: DinamicCacheObsApi }).__DINAMIC_CACHE_OBS__ = {
    getRecent: () => buffer.map(({ at, ...rest }) => ({ ...rest, at })),
    clear: () => {
      buffer.length = 0;
    },
    isActive: isCacheMutationObservabilityActive,
  };
}

export type DinamicCacheObsApi = {
  getRecent: () => Array<CacheMutationObservabilityEvent & { at: number }>;
  clear: () => void;
  isActive: () => boolean;
};

export function summarizeQueryKey(key: QueryKey): string {
  if (!Array.isArray(key)) return String(key);
  const head = key.slice(0, 8).map((p) => {
    if (p === null) return 'null';
    if (typeof p === 'object') return '[obj]';
    return String(p);
  });
  return head.join(' › ');
}

function pushEvent(event: CacheMutationObservabilityEvent): void {
  if (!isCacheMutationObservabilityActive()) return;
  const row: Timestamped = { ...event, at: Date.now() };
  buffer.push(row);
  if (buffer.length > MAX_EVENTS) buffer.splice(0, buffer.length - MAX_EVENTS);
  installWindowHook();
  if (isConsoleLoggingEnabled()) {
    // eslint-disable-next-line no-console -- Phase 8 dev-only diagnostics
    console.debug('[dinamic:cache-obs]', row.kind, row);
  }
  reportGuardrailsForNewEvent(row, buffer);
}

export function recordReviewActionCacheObs(event: Omit<ReviewActionCacheObsEvent, 'kind'>): void {
  pushEvent({ kind: 'review_action_cache', ...event });
}

export function recordNonReviewPatchObs(event: Omit<NonReviewPatchObsEvent, 'kind'>): void {
  pushEvent({ kind: 'non_review_patch', ...event });
}

export function recordMutationInvalidationsObs(
  event: Omit<MutationInvalidationsObsEvent, 'kind'>
): void {
  pushEvent({ kind: 'mutation_invalidations', ...event });
}

export function recordExplicitRefreshObs(event: Omit<ExplicitRefreshObsEvent, 'kind'>): void {
  pushEvent({ kind: 'explicit_refresh', ...event });
}

/** Test / devtools: snapshot of recent events (newest last). */
export function getCacheMutationObservabilityEvents(): Array<CacheMutationObservabilityEvent & { at: number }> {
  return buffer.map(({ at, ...rest }) => ({ ...rest, at } as CacheMutationObservabilityEvent & { at: number }));
}

export function clearCacheMutationObservabilityEvents(): void {
  buffer.length = 0;
}
