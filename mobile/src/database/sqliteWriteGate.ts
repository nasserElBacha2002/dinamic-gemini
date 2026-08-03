/**
 * Process-wide SQLite write coordination.
 * WAL + busy_timeout help, but concurrent BEGIN IMMEDIATE / exclusive txs still stampede
 * during capture finish (upload enqueue + offline ops + local scan). Serialize writers in JS
 * and retry SQLITE_BUSY after the native busy_timeout window.
 */

import { isSqliteBusyError } from './sqliteErrors';

/** Native SQLite busy_timeout (ms). Must stay aligned with PRAGMA in database.ts. */
export const SQLITE_BUSY_TIMEOUT_MS = 15_000;

/** JS-level busy retries after native timeout / race. */
export const SQLITE_BUSY_RETRY_ATTEMPTS = 6;
export const SQLITE_BUSY_RETRY_BASE_DELAY_MS = 40;

let writeTail: Promise<void> = Promise.resolve();

/** @internal test helper */
export function __resetSqliteWriteGateForTests(): void {
  writeTail = Promise.resolve();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Serialize exclusive writers so CaptureRepository BEGIN IMMEDIATE and
 * OfflineOperationRepository.withExclusiveTransactionAsync do not fight.
 */
export async function runExclusiveDbWrite<T>(fn: () => Promise<T>): Promise<T> {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const previous = writeTail;
  writeTail = previous.then(
    () => gate,
    () => gate,
  );
  await previous;
  try {
    return await fn();
  } finally {
    release();
  }
}

export async function withSqliteBusyRetry<T>(
  fn: () => Promise<T>,
  options?: {
    readonly maxAttempts?: number;
    readonly baseDelayMs?: number;
  },
): Promise<T> {
  const maxAttempts = options?.maxAttempts ?? SQLITE_BUSY_RETRY_ATTEMPTS;
  const baseDelayMs = options?.baseDelayMs ?? SQLITE_BUSY_RETRY_BASE_DELAY_MS;
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (!isSqliteBusyError(error) || attempt >= maxAttempts) {
        throw error;
      }
      const jitter = Math.floor(Math.random() * 40);
      await sleep(baseDelayMs * attempt + jitter);
    }
  }
  throw lastError;
}

/** Exclusive write + busy retry (typical for transactional mutations). */
export async function runExclusiveDbWriteWithBusyRetry<T>(fn: () => Promise<T>): Promise<T> {
  return runExclusiveDbWrite(() => withSqliteBusyRetry(fn));
}
