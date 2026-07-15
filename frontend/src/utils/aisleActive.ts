/**
 * Soft-active flag helpers. Missing `is_active` is treated as active for safety
 * (older API payloads / cached rows).
 */

export function isAisleActive(aisle: { is_active?: boolean } | null | undefined): boolean {
  return aisle?.is_active !== false;
}

/** Active aisles only — for selectors used by new operational flows. */
export function filterActiveAisles<T extends { is_active?: boolean }>(aisles: readonly T[]): T[] {
  return aisles.filter((a) => isAisleActive(a));
}
