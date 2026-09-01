import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { ConfirmedLocalResultRow } from '../../database/repositories/confirmedLocalResultRepository';
import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import {
  CHECKSUM_ALGORITHM,
  LOCAL_CSV_SCHEMA_VERSION,
  buildCsvDocument,
  sha256Hex,
  type LocalCsvRow,
} from './csvFormat';
import { createId } from '../../shared/createId';
import {
  parseDinamicPositionPayload,
  type ActivePositionState,
} from '../../core/positionLabelPayload';
import { parseStoredProductResults } from '../../core/storedProductResults';
import { parseStoredProductRejections } from '../../core/productLabelRejection';
import {
  buildSupplierImportNotes,
  isLikelyRawSegmentedPayload,
  positionFromRecognitionSnapshot,
  productsFromRecognitionSnapshot,
} from './supplierExportSemantics';

export interface LocalCsvExportInput {
  readonly session: CaptureSessionRow;
  readonly photos: readonly CapturePhotoRow[];
  readonly drafts: readonly LocalDetectionDraftRow[];
  readonly confirmed: readonly ConfirmedLocalResultRow[];
  readonly deviceId: string;
  readonly companyId: string | null;
  readonly clientId: string | null;
  readonly exportId?: string;
  readonly exportedAt?: string;
  readonly freezeId?: string | null;
  readonly freezeGeneration?: number | null;
}

export interface LocalCsvExportResult {
  readonly exportId: string;
  readonly exportedAt: string;
  readonly schemaVersion: string;
  readonly rowCount: number;
  readonly productResultCount: number;
  readonly positionEventCount: number;
  readonly rejectedDetectionCount: number;
  readonly checksumSha256: string;
  readonly checksumAlgorithm: 'sha256';
  readonly csv: string;
  readonly scope: 'session';
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
}

function cell(value: string | number | null | undefined): string {
  if (value == null) {
    return '';
  }
  return String(value);
}

type PositionFields = {
  positionCode: string;
  positionStatus: string;
  pallet: string;
  side: string;
  level: string;
  markerIndex: string;
  markerTotal: string;
  positionLabelId: string;
  positionPayloadRaw: string;
};

function fieldsFromActiveState(
  state: ActivePositionState,
  positionStatus: string,
): PositionFields {
  return {
    positionCode: state.displayName || state.labelId,
    positionStatus,
    pallet: state.pallet ?? '',
    side: state.side ?? '',
    level: state.level != null ? String(state.level) : '',
    markerIndex: state.markerIndex != null ? String(state.markerIndex) : '',
    markerTotal: state.markerTotal != null ? String(state.markerTotal) : '',
    positionLabelId: state.positionLabelId || state.labelId,
    // Exact ML Kit raw string — never rebuild from parsed subset.
    positionPayloadRaw: state.rawPayload || state.sourcePayload || '',
  };
}

function parsePositionSnapshotJson(raw: string | null | undefined): ActivePositionState | null {
  if (raw == null || !String(raw).trim()) return null;
  try {
    const parsed = JSON.parse(String(raw)) as Partial<ActivePositionState>;
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.labelId !== 'string' && typeof parsed.positionLabelId !== 'string') {
      return null;
    }
    return parsed as ActivePositionState;
  } catch {
    return null;
  }
}

function snapshotJsonFromDraftOrConfirmed(
  draft: LocalDetectionDraftRow | undefined,
  confirmed: ConfirmedLocalResultRow | undefined,
): string | null {
  const fromDraft = draft?.position_snapshot_json ?? null;
  if (fromDraft) return fromDraft;
  const fromConfirmed = (confirmed as { position_snapshot_json?: string | null } | undefined)
    ?.position_snapshot_json;
  return fromConfirmed ?? null;
}

function positionDetectedOnDraft(draft: LocalDetectionDraftRow | undefined): boolean {
  if (!draft) return false;
  if (Number(draft.position_detected) === 1) return true;
  return draft.error_code === 'POSITION_LABEL_DETECTED';
}

type EmitProduct = {
  readonly labelId: string;
  readonly internalCode: string | null;
  readonly quantity: number | null;
};

function productsForPhoto(
  draft: LocalDetectionDraftRow | undefined,
  confirmed: ConfirmedLocalResultRow | undefined,
): EmitProduct[] {
  const fromJson = parseStoredProductResults(draft?.product_results_json);
  if (fromJson.length > 0) {
    return fromJson.map((p) => ({
      labelId: p.labelId,
      internalCode: p.internalCode,
      quantity: p.quantity,
    }));
  }

  const fromSnapshot = productsFromRecognitionSnapshot(
    draft?.recognition_profile_snapshot_json ?? confirmed?.recognition_profile_snapshot_json,
  );
  if (fromSnapshot.length > 0) {
    return fromSnapshot;
  }

  const errorCode = (draft?.error_code || '').toUpperCase();
  const rejections = parseStoredProductRejections(draft?.rejections_json);
  // D1 MODE fail-closed: never revive scalar/legacy product rows.
  if (
    errorCode === 'D1_CANDIDATES_FAILED' ||
    errorCode.startsWith('D1_') ||
    rejections.length > 0
  ) {
    return [];
  }

  // Confirmed override (operator) or authentic legacy single draft without product_results_json.
  const code = confirmed?.confirmed_internal_code ?? draft?.internal_code;
  if (code && String(code).trim() && draft?.error_code !== 'POSITION_LABEL_DETECTED') {
    const trimmed = String(code).trim();
    if (isLikelyRawSegmentedPayload(trimmed)) {
      return [];
    }
    const labelId =
      (confirmed as { label_id?: string | null } | undefined)?.label_id ??
      draft?.label_id ??
      '';
    return [
      {
        labelId: String(labelId ?? ''),
        internalCode: String(code).trim(),
        quantity: confirmed?.confirmed_quantity ?? draft?.quantity ?? null,
      },
    ];
  }
  return [];
}

/**
 * Fail closed: ZIP handoff must not ship unresolved LOCAL_PENDING-only captures
 * (backend would stage photos with zero inventory results).
 */
export function assertLocalCsvRowsExportReady(rows: readonly LocalCsvRow[]): void {
  if (rows.length === 0) {
    throw new Error('PACKAGE_EXPORT_EMPTY: no hay fotos para exportar.');
  }
  const pending = rows.filter((r) => String(r.source).toUpperCase() === 'LOCAL_PENDING');
  if (pending.length > 0) {
    const photoIds = pending.map((r) => r.capture_photo_id).filter(Boolean).join(',');
    throw new Error(
      `PACKAGE_EXPORT_UNRESOLVED: ${pending.length} foto(s) sin detectar/confirmar (LOCAL_PENDING). Completá el escaneo local o la revisión antes de exportar el ZIP.` +
        (photoIds ? ` capture_photo_ids=${photoIds}` : ''),
    );
  }
  const products = rows.filter((r) => {
    const source = String(r.source).toUpperCase();
    if (source === 'LOCAL_POSITION_LABEL') {
      return false;
    }
    return String(r.internal_code ?? '').trim().length > 0;
  });
  if (products.length === 0) {
    throw new Error(
      'PACKAGE_EXPORT_NO_PRODUCTS: el export no tiene productos con código interno. Escaneá o confirmá al menos un SKU antes de exportar.',
    );
  }
}

export function buildLocalCsvRows(input: LocalCsvExportInput): LocalCsvRow[] {
  const exportId = input.exportId ?? createId();
  const exportedAt = input.exportedAt ?? new Date().toISOString();
  const draftByPhoto = new Map(input.drafts.map((d) => [d.capture_photo_id, d]));
  const confirmedByPhoto = new Map(input.confirmed.map((c) => [c.capture_photo_id, c]));

  const eligible = [...input.photos]
    .filter((p) => p.status !== 'excluded' && p.status !== 'rejected')
    .sort((a, b) => {
      const sa = a.sequence_number ?? Number.MAX_SAFE_INTEGER;
      const sb = b.sequence_number ?? Number.MAX_SAFE_INTEGER;
      if (sa !== sb) return sa - sb;
      if (a.date_added !== b.date_added) return a.date_added - b.date_added;
      return a.asset_id.localeCompare(b.asset_id);
    });

  // LEGACY_FORWARD_FILL: only used when drafts lack position_snapshot_json.
  let legacyPositionCode = '';
  let legacyPallet = '';
  let legacySide = '';
  let legacyLevel = '';
  let legacyMarkerIndex = '';
  let legacyMarkerTotal = '';

  const rows: LocalCsvRow[] = [];
  const emittedLabelIds = new Set<string>();

  for (const photo of eligible) {
    const draft = draftByPhoto.get(photo.id);
    const confirmed = confirmedByPhoto.get(photo.id);
    const detectedHere = positionDetectedOnDraft(draft);
    const snapshot = parsePositionSnapshotJson(
      snapshotJsonFromDraftOrConfirmed(draft, confirmed),
    );
    const supplierPosition = positionFromRecognitionSnapshot(
      draft?.recognition_profile_snapshot_json ?? confirmed?.recognition_profile_snapshot_json,
    );

    let position: PositionFields;
    if (snapshot) {
      position = fieldsFromActiveState(
        snapshot,
        detectedHere ? 'LABEL_DETECTED' : 'FROM_SNAPSHOT',
      );
    } else if (supplierPosition) {
      position = {
        positionCode: supplierPosition.positionCode,
        positionStatus: detectedHere ? 'LABEL_DETECTED' : 'FROM_SUPPLIER_SNAPSHOT',
        pallet: supplierPosition.pallet,
        side: supplierPosition.side,
        level: supplierPosition.level,
        markerIndex: '',
        markerTotal: '',
        positionLabelId: supplierPosition.positionLabelId,
        positionPayloadRaw: supplierPosition.positionPayloadRaw,
      };
    } else {
      const labelPositionCode =
        detectedHere && draft?.internal_code ? String(draft.internal_code).trim() : '';
      if (labelPositionCode) {
        legacyPositionCode = labelPositionCode;
        const parsed = parseDinamicPositionPayload(labelPositionCode);
        if (parsed?.pallet) {
          legacyPallet = parsed.pallet;
          legacySide = parsed.side ?? '';
          legacyLevel = parsed.level != null ? String(parsed.level) : '';
          legacyMarkerIndex = parsed.markerIndex != null ? String(parsed.markerIndex) : '';
          legacyMarkerTotal = parsed.markerTotal != null ? String(parsed.markerTotal) : '';
          legacyPositionCode = parsed.displayName;
        }
      }
      const positionCode = labelPositionCode
        ? legacyPositionCode || labelPositionCode
        : legacyPositionCode;
      const positionStatus = labelPositionCode
        ? 'LABEL_DETECTED'
        : legacyPositionCode
          ? 'INFERRED_FROM_PRIOR_LABEL'
          : '';
      position = {
        positionCode,
        positionStatus,
        pallet: legacyPallet,
        side: legacySide,
        level: legacyLevel,
        markerIndex: legacyMarkerIndex,
        markerTotal: legacyMarkerTotal,
        positionLabelId: '',
        positionPayloadRaw: '',
      };
    }

    const requiresReview =
      confirmed == null &&
      (draft == null ||
        draft.status === 'UNRESOLVED' ||
        draft.status === 'AMBIGUOUS' ||
        draft.status === 'FAILED' ||
        draft.status === 'INVALID');

    let products = productsForPhoto(draft, confirmed);
    products = products.filter((p) => {
      const lid = (p.labelId || '').trim();
      if (!lid) return true;
      if (emittedLabelIds.has(lid)) return false;
      emittedLabelIds.add(lid);
      return true;
    });

    const rawPayloadForNotes =
      supplierPosition?.positionPayloadRaw ??
      (draft?.internal_code && isLikelyRawSegmentedPayload(String(draft.internal_code).trim())
        ? String(draft.internal_code).trim()
        : null);

    const labelKind: 'ITEM' | 'POSITION' | null =
      products.length > 0 ? 'ITEM' : supplierPosition ? 'POSITION' : null;

    const importNotes =
      labelKind != null
        ? buildSupplierImportNotes({
            snapshotJson: draft?.recognition_profile_snapshot_json,
            rawPayload: rawPayloadForNotes,
            labelKind,
          })
        : null;

    const base = {
      schema_version: LOCAL_CSV_SCHEMA_VERSION,
      export_id: exportId,
      exported_at: exportedAt,
      device_id: input.deviceId,
      company_id: cell(input.companyId),
      client_id: cell(input.clientId),
      inventory_id: input.session.inventory_id,
      inventory_name: input.session.inventory_name,
      aisle_id: input.session.aisle_id,
      aisle_code: input.session.aisle_name,
      capture_session_id: input.session.id,
      capture_photo_id: photo.id,
      client_file_id: cell(photo.client_file_id),
      capture_order: cell(photo.sequence_number),
      captured_at: cell(photo.stable_at ?? photo.detected_at ?? photo.created_at),
      position_code: position.positionCode,
      position_status: position.positionStatus,
      pallet: position.pallet,
      side: position.side,
      level: position.level,
      marker_index: position.markerIndex,
      marker_total: position.markerTotal,
      position_label_id: position.positionLabelId,
      position_payload_raw: position.positionPayloadRaw,
      quantity_status: cell(confirmed?.quantity_status ?? draft?.quantity_status),
      detection_status: cell(confirmed ? 'CONFIRMED' : draft?.status ?? photo.status),
      detector_version: cell(confirmed?.detector_version ?? draft?.detector_version),
      parser_version: cell(confirmed?.parser_version ?? draft?.parser_version),
      prepared_asset_fingerprint: cell(
        confirmed?.prepared_asset_sha256 ?? draft?.prepared_asset_fingerprint,
      ),
      requires_review: requiresReview ? 'true' : 'false',
      confirmed_manually: confirmed ? 'true' : 'false',
      error_code: cell(draft?.error_code ?? photo.stability_error),
      notes: cell(importNotes ?? ''),
      freeze_id: cell(input.freezeId ?? input.session.active_freeze_id),
      freeze_generation: cell(input.freezeGeneration ?? input.session.capture_freeze_generation),
    };

    if (products.length === 0) {
      const isPositionOnly = detectedHere || supplierPosition != null;
      rows.push({
        ...base,
        internal_code: '',
        label_id: '',
        quantity: '',
        quantity_status: isPositionOnly ? 'NOT_APPLICABLE' : base.quantity_status,
        source: confirmed
          ? confirmed.source
          : isPositionOnly
            ? 'LOCAL_POSITION_LABEL'
            : 'LOCAL_PENDING',
      });
      continue;
    }

    for (const product of products) {
      rows.push({
        ...base,
        internal_code: product.internalCode ?? '',
        label_id: cell(product.labelId),
        quantity: cell(product.quantity),
        quantity_status:
          product.quantity != null ? cell(confirmed?.quantity_status ?? draft?.quantity_status ?? 'PRESENT') : 'MISSING',
        source: confirmed ? confirmed.source : 'LOCAL_CODE_SCAN',
      });
    }
  }

  return rows;
}

export async function buildLocalCsvExport(input: LocalCsvExportInput): Promise<LocalCsvExportResult> {
  const rows = buildLocalCsvRows(input);
  assertLocalCsvRowsExportReady(rows);
  const exportId = rows[0]?.export_id ?? input.exportId ?? createId();
  const exportedAt = rows[0]?.exported_at ?? input.exportedAt ?? new Date().toISOString();
  const csv = buildCsvDocument(rows);
  const checksumSha256 = await sha256Hex(csv);
  const productResultCount = rows.filter((r) => r.source === 'LOCAL_CODE_SCAN').length;
  const positionEventCount = rows.filter((r) => r.source === 'LOCAL_POSITION_LABEL').length;
  const rejectedDetectionCount = input.drafts.reduce((acc, d) => {
    const fromJson = parseStoredProductRejections(d.rejections_json).length;
    if (fromJson > 0) return acc + fromJson;
    if (!d.product_results_json && d.error_code === 'D1_CANDIDATES_FAILED') return acc + 1;
    return acc;
  }, 0);
  return {
    exportId,
    exportedAt,
    schemaVersion: LOCAL_CSV_SCHEMA_VERSION,
    rowCount: rows.length,
    productResultCount,
    positionEventCount,
    rejectedDetectionCount,
    checksumSha256,
    checksumAlgorithm: CHECKSUM_ALGORITHM,
    csv,
    scope: 'session',
    freezeId: input.freezeId ?? input.session.active_freeze_id ?? null,
    freezeGeneration: input.freezeGeneration ?? input.session.capture_freeze_generation ?? null,
  };
}
