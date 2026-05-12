/**
 * Optional query-string serialization for API clients using `URLSearchParams`.
 *
 * Wire output for list endpoints must stay aligned with `queryParamCanonicalization.ts`
 * where those modules use canonical params as React Query keys (P1/P2 migrated builders only).
 *
 * Path segments stay `encodeURIComponent` in each API module; this helper is query-only.
 */

export type QueryParamValue = string | number | boolean | null | undefined;

export type BooleanEmitMode = 'always' | 'true-only' | 'false-only';

export interface QueryParamOptions {
  min?: number;
  trim?: boolean;
  /** Applied to string values after the trim step (or raw string when `trim: false`). Omit entry if result is empty. */
  transform?: (value: string) => string;
  /** For booleans only; strings and numbers ignore this. Default `always`. */
  emit?: BooleanEmitMode;
}

export type QueryParamEntry = readonly [key: string, value: QueryParamValue, options?: QueryParamOptions];

export function buildQueryString(entries: readonly QueryParamEntry[]): string {
  const params = new URLSearchParams();

  for (const [key, value, options] of entries) {
    if (value == null) continue;

    if (typeof value === 'string') {
      let finalValue = options?.trim === false ? value : value.trim();
      if (finalValue === '') continue;
      if (options?.transform) {
        finalValue = options.transform(finalValue);
        if (finalValue === '') continue;
      }
      params.set(key, finalValue);
      continue;
    }

    if (typeof value === 'number') {
      if (!Number.isFinite(value)) continue;
      if (options?.min != null && value < options.min) continue;
      params.set(key, String(value));
      continue;
    }

    if (typeof value === 'boolean') {
      const emit = options?.emit ?? 'always';
      if (emit === 'true-only' && value !== true) continue;
      if (emit === 'false-only' && value !== false) continue;
      params.set(key, String(value));
    }
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}
