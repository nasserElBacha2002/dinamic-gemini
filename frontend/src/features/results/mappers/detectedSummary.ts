/**
 * Safe accessors for position detected_summary_json (arbitrary backend shape).
 * Use these instead of casting to Record<string, unknown> to avoid fragile access.
 */

/**
 * Returns a string value from a summary-like object if present and string-coercible; otherwise null.
 */
export function getSummaryString(
  obj: unknown,
  key: string
): string | null {
  if (obj == null || typeof obj !== 'object') return null;
  const val = (obj as Record<string, unknown>)[key];
  if (val == null) return null;
  if (typeof val === 'string' && val.trim() !== '') return val.trim();
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  return null;
}

/**
 * Returns a number value from a summary-like object if present and numeric; otherwise null.
 */
export function getSummaryNumber(
  obj: unknown,
  key: string
): number | null {
  if (obj == null || typeof obj !== 'object') return null;
  const val = (obj as Record<string, unknown>)[key];
  if (val == null) return null;
  if (typeof val === 'number' && Number.isFinite(val)) return val;
  if (typeof val === 'string' && val.trim() !== '') {
    const n = Number(val.trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}
