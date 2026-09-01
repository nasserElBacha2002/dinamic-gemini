import { sha256Hex } from '../localCsv/csvFormat';
import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type {
  CaptureLabelKind,
  CaptureResultKind,
  OfflineAisleCaptureV1,
  OfflineAisleItemResult,
  OfflineAisleKindProvenance,
  OfflineAislePositionResult,
  OfflineAisleProfileEntryV1,
} from './types';
import { OfflineAisleExportError } from './errors';

type SnapshotBranch = {
  readonly status?: string;
  readonly profile_id?: string | null;
  readonly profile_version?: number | null;
  readonly profile_source?: string | null;
  readonly label_id?: string | null;
  readonly sku?: string | null;
  readonly quantity?: number | null;
  readonly position_id?: string | null;
  readonly pallet?: string | null;
  readonly side?: string | null;
  readonly level?: string | null;
};

type ParsedSnapshot = {
  readonly clientSupplierId: string | null;
  readonly item: SnapshotBranch | null;
  readonly position: SnapshotBranch | null;
};

export interface ParsedProductWithRaw {
  readonly labelId: string | null;
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly rawPayload: string | null;
  readonly formatVersion?: string;
  readonly validationStatus?: string;
}

function parseRecognitionSnapshot(raw: string | null | undefined): ParsedSnapshot | null {
  if (!raw?.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as {
      client_supplier_id?: string | null;
      item?: SnapshotBranch;
      position?: SnapshotBranch;
    };
    return {
      clientSupplierId: parsed.client_supplier_id ?? null,
      item: parsed.item ?? null,
      position: parsed.position ?? null,
    };
  } catch {
    return null;
  }
}

export function parseProductResultsWithRaw(
  raw: string | null | undefined,
): ParsedProductWithRaw[] {
  if (raw == null || !String(raw).trim()) return [];
  try {
    const parsed = JSON.parse(String(raw)) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: ParsedProductWithRaw[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const row = item as Record<string, unknown>;
      const labelIdRaw = typeof row.labelId === 'string' ? row.labelId.trim() : '';
      const labelId = labelIdRaw || null;
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
      const rawPayload =
        typeof row.rawPayload === 'string' && row.rawPayload.length > 0
          ? row.rawPayload
          : null;
      const formatVersion =
        typeof row.formatVersion === 'string' ? row.formatVersion : undefined;
      const validationStatus =
        typeof row.validationStatus === 'string' ? row.validationStatus : undefined;
      const hasSemantic =
        labelId != null ||
        internalCode != null ||
        quantity != null ||
        rawPayload != null;
      if (!hasSemantic) continue;
      out.push({
        labelId,
        internalCode,
        quantity,
        rawPayload,
        ...(formatVersion ? { formatVersion } : {}),
        ...(validationStatus ? { validationStatus } : {}),
      });
    }
    return out;
  } catch {
    return [];
  }
}

function positionRawFromSnapshot(json: string | null | undefined): string | null {
  if (!json?.trim()) return null;
  try {
    const parsed = JSON.parse(json) as { rawPayload?: string; sourcePayload?: string };
    if (typeof parsed.rawPayload === 'string' && parsed.rawPayload.length > 0) {
      return parsed.rawPayload;
    }
    if (typeof parsed.sourcePayload === 'string' && parsed.sourcePayload.length > 0) {
      return parsed.sourcePayload;
    }
    return null;
  } catch {
    return null;
  }
}

function profileRef(profileId: string, version: number, kind: 'ITEM' | 'POSITION'): string {
  return `${kind.toLowerCase()}:${profileId}:v${version}`;
}

function provenanceFromBranch(
  branch: SnapshotBranch | null | undefined,
  kind: 'ITEM' | 'POSITION',
  snap: ParsedSnapshot | null,
  aisleSupplierId: string | null,
  rawPayload: string | null,
): OfflineAisleKindProvenance | null {
  if (!branch?.profile_id || branch.profile_version == null) {
    if (!rawPayload) return null;
    return {
      source: branch?.profile_source ?? 'UNKNOWN',
      client_supplier_id: snap?.clientSupplierId ?? aisleSupplierId,
      profile_id: null,
      profile_version: null,
      profile_ref: null,
      raw_evidence: {
        raw_payload: rawPayload,
        raw_payload_sha256: null,
      },
    };
  }
  const ref = profileRef(branch.profile_id, branch.profile_version, kind);
  return {
    source: branch.profile_source ?? 'SUPPLIER',
    client_supplier_id: snap?.clientSupplierId ?? aisleSupplierId,
    profile_id: branch.profile_id,
    profile_version: branch.profile_version,
    profile_ref: ref,
    raw_evidence: {
      raw_payload: rawPayload,
      raw_payload_sha256: null,
    },
  };
}

function itemResultFromSnapshot(snap: ParsedSnapshot | null): OfflineAisleItemResult | null {
  if (!snap?.item || snap.item.status !== 'VALID') return null;
  return {
    label_id: snap.item.label_id ?? null,
    sku: snap.item.sku ?? null,
    quantity:
      snap.item.quantity == null
        ? null
        : Number.isFinite(Number(snap.item.quantity))
          ? Number(snap.item.quantity)
          : null,
  };
}

function positionResultFromSnapshot(snap: ParsedSnapshot | null): OfflineAislePositionResult | null {
  if (!snap?.position || snap.position.status !== 'VALID') return null;
  return {
    position_id: snap.position.position_id ?? null,
    pallet: snap.position.pallet ?? null,
    side: snap.position.side ?? null,
    level:
      snap.position.level != null && snap.position.level !== ''
        ? String(snap.position.level)
        : null,
  };
}

function itemResultFromProduct(p: ParsedProductWithRaw): OfflineAisleItemResult {
  const labelId = (p.labelId ?? '').trim();
  return {
    label_id: labelId || null,
    sku: p.internalCode,
    quantity: p.quantity,
  };
}

function resolveResultKind(
  hasProduct: boolean,
  hasPosition: boolean,
  draft: LocalDetectionDraftRow | undefined,
): CaptureResultKind {
  if (hasProduct && hasPosition) return 'PRODUCT_WITH_POSITION';
  if (hasProduct) return 'PRODUCT';
  if (hasPosition) return 'POSITION_ONLY';
  if (
    draft?.status === 'UNRESOLVED' ||
    draft?.status === 'FAILED' ||
    draft?.status === 'INVALID' ||
    draft?.status === 'AMBIGUOUS'
  ) {
    return draft.status === 'AMBIGUOUS' ? 'MANUAL_REVIEW' : 'UNRECOGNIZED';
  }
  return 'UNRECOGNIZED';
}

function resolveLabelKind(resultKind: CaptureResultKind): CaptureLabelKind {
  if (resultKind === 'POSITION_ONLY') return 'POSITION';
  if (resultKind === 'PRODUCT' || resultKind === 'PRODUCT_WITH_POSITION') return 'ITEM';
  return 'UNRECOGNIZED';
}

function isSupplierItem(
  primary: ParsedProductWithRaw | null,
  snap: ParsedSnapshot | null,
): boolean {
  return (
    primary?.formatVersion === 'SUPPLIER' || snap?.item?.profile_source === 'SUPPLIER'
  );
}

function isSupplierPosition(snap: ParsedSnapshot | null): boolean {
  return snap?.position?.profile_source === 'SUPPLIER';
}

function validateSupplierProvenance(
  captureId: string,
  kind: 'ITEM' | 'POSITION',
  supplier: boolean,
  resultKind: CaptureResultKind,
  provenance: OfflineAisleKindProvenance | null,
): void {
  if (!supplier || resultKind === 'UNRECOGNIZED') return;
  if (!provenance?.raw_evidence.raw_payload) {
    throw new OfflineAisleExportError(
      'RAW_EVIDENCE_MISSING',
      `falta raw_payload supplier (${kind}) en capture ${captureId}`,
    );
  }
  if (!provenance.profile_id) {
    throw new OfflineAisleExportError(
      'PROFILE_METADATA_INCOMPLETE',
      `falta profile metadata (${kind}) en capture ${captureId}`,
    );
  }
}

export function mapPhotoToCapture(input: {
  readonly photo: CapturePhotoRow;
  readonly session: CaptureSessionRow;
  readonly aisleId: string;
  readonly aisleClientSupplierId: string | null;
  readonly draft: LocalDetectionDraftRow | undefined;
  readonly includeAssets: boolean;
  readonly requireAssets: boolean;
}): OfflineAisleCaptureV1 {
  const { photo, session, draft, aisleId, aisleClientSupplierId } = input;
  const snap = parseRecognitionSnapshot(draft?.recognition_profile_snapshot_json);
  const products = parseProductResultsWithRaw(draft?.product_results_json);
  const primary = products[0] ?? null;

  const positionFromSnap = positionResultFromSnapshot(snap);
  const positionRaw = positionRawFromSnapshot(draft?.position_snapshot_json);
  const positionDetected =
    Number(draft?.position_detected) === 1 ||
    draft?.error_code === 'POSITION_LABEL_DETECTED' ||
    positionFromSnap != null ||
    Boolean(positionRaw);

  const itemFromSnap = itemResultFromSnapshot(snap);
  const hasProduct = Boolean(primary || itemFromSnap);
  const hasPosition = positionDetected && (positionFromSnap != null || Boolean(positionRaw));

  const resultKind = resolveResultKind(hasProduct, hasPosition, draft);
  const labelKind = resolveLabelKind(resultKind);

  const itemRaw = hasProduct ? (primary?.rawPayload ?? null) : null;
  const positionRawFinal = hasPosition ? positionRaw : null;

  const itemProvenance = hasProduct
    ? provenanceFromBranch(snap?.item, 'ITEM', snap, aisleClientSupplierId, itemRaw)
    : null;
  const positionProvenance = hasPosition
    ? provenanceFromBranch(
        snap?.position,
        'POSITION',
        snap,
        aisleClientSupplierId,
        positionRawFinal,
      )
    : null;

  if (hasProduct && isSupplierItem(primary, snap)) {
    validateSupplierProvenance(
      photo.id,
      'ITEM',
      true,
      resultKind,
      itemProvenance,
    );
  }
  if (hasPosition && isSupplierPosition(snap)) {
    validateSupplierProvenance(
      photo.id,
      'POSITION',
      true,
      resultKind,
      positionProvenance,
    );
  }

  const productResult: OfflineAisleItemResult | null = hasProduct
    ? primary
      ? itemResultFromProduct(primary)
      : itemFromSnap
    : null;

  const positionResult: OfflineAislePositionResult | null = hasPosition
    ? positionFromSnap ??
      (positionRawFinal
        ? {
            position_id: null,
            pallet: null,
            side: null,
            level: null,
          }
        : null)
    : null;

  const requiresReview =
    draft == null ||
    draft.status === 'UNRESOLVED' ||
    draft.status === 'AMBIGUOUS' ||
    draft.status === 'FAILED' ||
    draft.status === 'INVALID' ||
    draft.status === 'DETECTED_UNVERIFIED';

  const assetExt =
    (photo.display_name && /\.[a-z0-9]+$/i.exec(photo.display_name)?.[0]) || '.jpg';
  const assetPath = input.includeAssets ? `assets/${photo.id}${assetExt}` : null;

  return {
    capture_id: photo.id,
    capture_session_id: session.id,
    aisle_id: aisleId,
    client_file_id: photo.client_file_id,
    sequence_number: photo.sequence_number,
    created_at: photo.stable_at ?? photo.detected_at ?? photo.created_at,
    label_kind: labelKind,
    result_kind: resultKind,
    status: draft?.status ?? 'UNRECOGNIZED',
    error_code: draft?.error_code ?? null,
    requires_review: requiresReview,
    recognitions: {
      item: itemProvenance,
      position: positionProvenance,
    },
    result: {
      product: productResult,
      position: positionResult,
    },
    asset: {
      included: input.includeAssets,
      asset_id: photo.asset_id,
      path: assetPath,
      mime_type: photo.mime_type || 'image/jpeg',
      size_bytes: null,
      sha256: null,
    },
    recognition_profile_snapshot_json: draft?.recognition_profile_snapshot_json ?? null,
  };
}

async function hashProvenance(
  provenance: OfflineAisleKindProvenance | null,
): Promise<OfflineAisleKindProvenance | null> {
  if (!provenance) return null;
  const raw = provenance.raw_evidence.raw_payload;
  const hash = raw ? await sha256Hex(raw) : null;
  return {
    ...provenance,
    raw_evidence: {
      raw_payload: raw,
      raw_payload_sha256: hash,
    },
  };
}

export async function finalizeCaptureRawHashes(
  captures: OfflineAisleCaptureV1[],
): Promise<OfflineAisleCaptureV1[]> {
  const out: OfflineAisleCaptureV1[] = [];
  for (const cap of captures) {
    out.push({
      ...cap,
      recognitions: {
        item: await hashProvenance(cap.recognitions.item),
        position: await hashProvenance(cap.recognitions.position),
      },
    });
  }
  return out;
}

function profileEntryFromProvenance(
  provenance: OfflineAisleKindProvenance,
  kind: 'ITEM' | 'POSITION',
  snapshot: Record<string, unknown> | null,
): OfflineAisleProfileEntryV1 | null {
  if (!provenance.profile_id || provenance.profile_version == null || !provenance.profile_ref) {
    return null;
  }
  return {
    profile_ref: provenance.profile_ref,
    label_kind: kind,
    client_supplier_id: provenance.client_supplier_id,
    source: provenance.source,
    profile_id: provenance.profile_id,
    profile_version: provenance.profile_version,
    snapshot,
  };
}

export function collectProfileEntries(
  captures: readonly OfflineAisleCaptureV1[],
): OfflineAisleProfileEntryV1[] {
  const byRef = new Map<string, OfflineAisleProfileEntryV1>();
  for (const cap of captures) {
    let snapshot: Record<string, unknown> | null = null;
    if (cap.recognition_profile_snapshot_json) {
      try {
        snapshot = JSON.parse(cap.recognition_profile_snapshot_json) as Record<string, unknown>;
      } catch {
        snapshot = null;
      }
    }
    for (const [kind, provenance] of [
      ['ITEM', cap.recognitions.item] as const,
      ['POSITION', cap.recognitions.position] as const,
    ]) {
      if (!provenance) continue;
      const ref = provenance.profile_ref;
      if (!ref || byRef.has(ref)) continue;
      const entry = profileEntryFromProvenance(provenance, kind, snapshot);
      if (entry) byRef.set(ref, entry);
    }
  }
  return [...byRef.values()].sort((a, b) => a.profile_ref.localeCompare(b.profile_ref));
}

export function sortCapturesDeterministic(
  captures: readonly OfflineAisleCaptureV1[],
): OfflineAisleCaptureV1[] {
  return [...captures].sort((a, b) => {
    const ta = a.created_at ?? '';
    const tb = b.created_at ?? '';
    if (ta !== tb) return ta.localeCompare(tb);
    return a.capture_id.localeCompare(b.capture_id);
  });
}
