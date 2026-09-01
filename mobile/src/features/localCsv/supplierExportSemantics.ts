/**
 * Supplier-aware CSV export helpers — prevent raw segmented payloads from becoming SKU.
 */

export function isLikelyRawSegmentedPayload(value: string | null | undefined): boolean {
  const text = (value ?? '').trim();
  if (!text.includes('|')) {
    return false;
  }
  return text.split('|').length >= 3;
}

export interface SupplierExportProduct {
  readonly labelId: string;
  readonly internalCode: string | null;
  readonly quantity: number | null;
}

export interface SupplierExportPosition {
  readonly positionCode: string;
  readonly positionLabelId: string;
  readonly pallet: string;
  readonly side: string;
  readonly level: string;
  readonly positionPayloadRaw: string;
}

type SnapshotBranch = {
  readonly status?: string;
  readonly label_id?: string | null;
  readonly sku?: string | null;
  readonly quantity?: number | null;
  readonly position_id?: string | null;
  readonly pallet?: string | null;
  readonly side?: string | null;
  readonly level?: string | null;
  readonly profile_id?: string | null;
  readonly profile_version?: number | null;
};

function parseSnapshot(raw: string | null | undefined): {
  item: SnapshotBranch | null;
  position: SnapshotBranch | null;
  clientSupplierId: string | null;
} | null {
  if (!raw?.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as {
      client_supplier_id?: string | null;
      item?: SnapshotBranch;
      position?: SnapshotBranch;
    };
    return {
      item: parsed.item ?? null,
      position: parsed.position ?? null,
      clientSupplierId: parsed.client_supplier_id ?? null,
    };
  } catch {
    return null;
  }
}

export function productsFromRecognitionSnapshot(
  raw: string | null | undefined,
): SupplierExportProduct[] {
  const snap = parseSnapshot(raw);
  if (!snap?.item || snap.item.status !== 'VALID') {
    return [];
  }
  const labelId = (snap.item.label_id ?? '').trim();
  const sku = (snap.item.sku ?? '').trim() || null;
  const qty = snap.item.quantity;
  const quantity =
    qty == null ? null : Number.isFinite(Number(qty)) ? Number(qty) : null;
  if (!labelId && !sku) {
    return [];
  }
  return [{ labelId: labelId || sku || '', internalCode: sku, quantity }];
}

export function positionFromRecognitionSnapshot(
  raw: string | null | undefined,
): SupplierExportPosition | null {
  const snap = parseSnapshot(raw);
  if (!snap?.position || snap.position.status !== 'VALID') {
    return null;
  }
  const positionId = (snap.position.position_id ?? '').trim();
  if (!positionId) {
    return null;
  }
  const pallet = (snap.position.pallet ?? '').trim();
  const side = (snap.position.side ?? '').trim().toUpperCase();
  const level = snap.position.level != null ? String(snap.position.level).trim() : '';
  const rawPayload = [positionId, pallet, side, level].filter(Boolean).join('|');
  return {
    positionCode: positionId,
    positionLabelId: positionId,
    pallet,
    side,
    level,
    positionPayloadRaw: rawPayload.includes('|') ? rawPayload : positionId,
  };
}

/** Compact JSON for backend revalidation (stored in CSV `notes`, max ~512 chars target). */
export function buildSupplierImportNotes(input: {
  readonly snapshotJson: string | null | undefined;
  readonly rawPayload?: string | null;
  readonly labelKind?: 'ITEM' | 'POSITION';
}): string | null {
  const snap = parseSnapshot(input.snapshotJson);
  if (!snap) {
    return null;
  }
  const branch = input.labelKind === 'POSITION' ? snap.position : snap.item;
  if (!branch?.profile_id || branch.profile_version == null) {
    return null;
  }
  const payload = {
    supplier_import: {
      client_supplier_id: snap.clientSupplierId,
      label_kind: input.labelKind ?? 'ITEM',
      profile_id: branch.profile_id,
      profile_version: branch.profile_version,
      raw_payload: input.rawPayload ?? null,
    },
  };
  try {
    return JSON.stringify(payload);
  } catch {
    return null;
  }
}
