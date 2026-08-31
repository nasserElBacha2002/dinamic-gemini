/**
 * Persist/export helpers for 0..N product results stored on a local detection draft.
 */

export type StoredProductResult = {
  readonly labelId: string;
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly validationStatus?: string;
  readonly formatVersion?: string;
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
      if (!labelId) continue;
      const internalCodeRaw =
        typeof row.internalCode === 'string' ? row.internalCode.trim() : '';
      const internalCode = internalCodeRaw || null;
      let quantity: number | null = null;
      if (row.quantity === null || row.quantity === undefined) {
        quantity = null;
      } else if (typeof row.quantity === 'number' && Number.isFinite(row.quantity)) {
        quantity = row.quantity;
      } else {
        const n = Number(row.quantity);
        quantity = Number.isFinite(n) ? n : null;
      }
      // Legacy Dinamic rows required internalCode + finite quantity; keep them.
      // SUPPLIER identity-only allows null internalCode / null quantity with labelId.
      const formatVersion =
        typeof row.formatVersion === 'string' ? row.formatVersion : undefined;
      const isSupplierIdentity =
        formatVersion === 'SUPPLIER' || (internalCode == null && quantity == null);
      if (!isSupplierIdentity && (internalCode == null || quantity == null)) {
        continue;
      }
      const validationStatus =
        typeof row.validationStatus === 'string' ? row.validationStatus : undefined;
      out.push({
        labelId,
        internalCode,
        quantity,
        ...(validationStatus ? { validationStatus } : {}),
        ...(formatVersion ? { formatVersion } : {}),
      });
    }
    return out;
  } catch {
    return [];
  }
}
