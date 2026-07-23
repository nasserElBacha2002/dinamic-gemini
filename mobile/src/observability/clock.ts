/**
 * Monotonic duration helper. Prefer `performance.now()` when available;
 * fall back to `Date.now()` (wall clock) for Node/Jest without performance API.
 */

export interface MonotonicClock {
  nowMs(): number;
}

export function createMonotonicClock(
  nowFn: () => number = () => {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
      return performance.now();
    }
    return Date.now();
  },
): MonotonicClock {
  return {
    nowMs: () => nowFn(),
  };
}

export function elapsedMs(clock: MonotonicClock, startedAt: number): number {
  return Math.max(0, Math.round(clock.nowMs() - startedAt));
}

export function wallTimestamp(now: () => Date = () => new Date()): string {
  return now().toISOString();
}
