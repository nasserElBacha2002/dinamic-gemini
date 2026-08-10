/**
 * Persist/export helpers for 0..N product results stored on a local detection draft.
 */

export type StoredProductResult = {
  readonly labelId: string;
  readonly internalCode: string;
  readonly quantity: number;
  readonly validationStatus?: string;
};

export function parseStoredProductResults(
  raw: string | null | undefined,
): StoredProductResult[] {
  if (raw == null || !String(raw).trim()) return [];
  try {
    const parsed = JSON.parse(String(raw)) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: StoredProductResult[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const labelId = typeof row.labelId === 'string' ? row.labelId.trim() : '';
      const internalCode =
        typeof row.internalCode === 'string' ? row.internalCode.trim() : '';
      const quantity = typeof row.quantity === 'number' ? row.quantity : Number(row.quantity);
      if (!labelId || !internalCode || !Number.isFinite(quantity)) continue;
      const validationStatus =
        typeof row.validationStatus === 'string' ? row.validationStatus : undefined;
      out.push(
        validationStatus
          ? { labelId, internalCode, quantity, validationStatus }
          : { labelId, internalCode, quantity },
      );
    }
    return out;
  } catch {
    return [];
  }
}
