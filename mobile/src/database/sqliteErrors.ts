/** Shared SQLite error helpers (no expo-sqlite import — safe for Jest core config). */

export function isSqliteMalformedError(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error);
  return /malformed|SQLITE_CORRUPT|disk image is malformed|file is not a database/i.test(msg);
}
