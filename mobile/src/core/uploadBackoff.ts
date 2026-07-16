/** Exponential backoff with jitter. Pure — unit-testable. */
export function computeRetryDelayMs(input: {
  readonly attempt: number;
  readonly baseDelayMs: number;
  readonly maxDelayMs?: number;
  readonly jitterRatio?: number;
  readonly random?: () => number;
}): number {
  const attempt = Math.max(0, input.attempt);
  const base = Math.max(0, input.baseDelayMs);
  const maxDelay = input.maxDelayMs ?? 60_000;
  const jitterRatio = input.jitterRatio ?? 0.2;
  const random = input.random ?? Math.random;
  const exp = Math.min(maxDelay, base * 2 ** attempt);
  const jitter = exp * jitterRatio * random();
  return Math.min(maxDelay, Math.floor(exp + jitter));
}
