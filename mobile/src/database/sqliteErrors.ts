/** Shared SQLite error helpers (no expo-sqlite import — safe for Jest core config). */

export function isSqliteMalformedError(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error);
  return /malformed|SQLITE_CORRUPT|disk image is malformed|file is not a database/i.test(msg);
}

/** SQLITE_BUSY / locked — often surfaced via NativeStatement.finalizeAsync. */
export function isSqliteBusyError(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    /database is locked|SQLITE_BUSY|error code\s*\u0005|error code\s*5\b/i.test(msg) ||
    (/nativestatement\.finalizeasync/i.test(msg) && /locked|busy/i.test(msg))
  );
}
