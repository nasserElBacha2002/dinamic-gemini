/**
 * Explicit product-label rejection from local CODE_SCAN consolidation.
 * Observable only — never creates a ProductResult / CSV product row.
 */

export type ProductLabelRejectionStatus =
  | 'D1_CHECKSUM_FAILED'
  | 'D1_MALFORMED'
  | 'UNKNOWN_VERSION'
  | 'QUANTITY_CONFLICT'
  | 'DUPLICATE_LABEL'
  | string;

export type ProductLabelRejection = {
  readonly labelId: string | null;
  readonly validationStatus: ProductLabelRejectionStatus;
  readonly reason: string;
  readonly rawValuePreview?: string;
  readonly detectionIndex?: number;
};

export function parseStoredProductRejections(
  raw: string | null | undefined,
): ProductLabelRejection[] {
  if (raw == null || !String(raw).trim()) return [];
  try {
    const parsed = JSON.parse(String(raw)) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: ProductLabelRejection[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const validationStatus =
        typeof row.validationStatus === 'string' ? row.validationStatus.trim() : '';
      if (!validationStatus) continue;
      const labelId =
        typeof row.labelId === 'string' && row.labelId.trim()
          ? row.labelId.trim().toUpperCase()
          : null;
      const reason =
        typeof row.reason === 'string' && row.reason.trim()
          ? row.reason.trim()
          : validationStatus;
      const detectionIndex =
        typeof row.detectionIndex === 'number' && Number.isFinite(row.detectionIndex)
          ? row.detectionIndex
          : undefined;
      const rawValuePreview =
        typeof row.rawValuePreview === 'string' ? row.rawValuePreview : undefined;
      out.push({
        labelId,
        validationStatus,
        reason,
        ...(detectionIndex !== undefined ? { detectionIndex } : {}),
        ...(rawValuePreview !== undefined ? { rawValuePreview } : {}),
      });
    }
    return out;
  } catch {
    return [];
  }
}

export function serializeProductRejections(
  rejections: readonly ProductLabelRejection[],
): string | null {
  if (!rejections.length) return null;
  return JSON.stringify(
    rejections.map((r) => ({
      labelId: r.labelId,
      validationStatus: r.validationStatus,
      reason: r.reason,
      ...(r.detectionIndex !== undefined ? { detectionIndex: r.detectionIndex } : {}),
      ...(r.rawValuePreview !== undefined ? { rawValuePreview: r.rawValuePreview } : {}),
    })),
  );
}
