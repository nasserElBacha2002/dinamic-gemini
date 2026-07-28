/**
 * Phase 9 — exponential backoff with jitter (pure).
 */

const DEFAULT_SCHEDULE_MS = [
  5_000,
  15_000,
  45_000,
  120_000,
  300_000,
  900_000,
  3_600_000,
] as const;

export function computeBackoffMs(
  attemptCount: number,
  scheduleMs: readonly number[] = DEFAULT_SCHEDULE_MS,
  random: () => number = Math.random,
): number {
  const idx = Math.max(0, Math.min(attemptCount, scheduleMs.length - 1));
  const base = scheduleMs[idx]!;
  const jitter = Math.floor(base * 0.2 * random());
  return base + jitter;
}

export function nextRetryIso(
  nowMs: number,
  attemptCount: number,
  random: () => number = Math.random,
): string {
  return new Date(nowMs + computeBackoffMs(attemptCount, DEFAULT_SCHEDULE_MS, random)).toISOString();
}

export { DEFAULT_SCHEDULE_MS as OFFLINE_RETRY_SCHEDULE_MS };
