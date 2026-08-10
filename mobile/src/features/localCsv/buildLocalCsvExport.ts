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
import { parseDinamicPositionPayload } from '../../core/positionLabelPayload';

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
    throw new Error(
      `PACKAGE_EXPORT_UNRESOLVED: ${pending.length} foto(s) sin detectar/confirmar (LOCAL_PENDING). Completá el escaneo local o la revisión antes de exportar el ZIP.`,
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

  /** Last DINAMIC_POSITION key seen in capture order — applies to following product photos. */
  let currentPositionCode = '';
  let currentPallet = '';
  let currentSide = '';
  let currentLevel = '';
  let currentMarkerIndex = '';
  let currentMarkerTotal = '';

  return eligible.map((photo) => {
    const draft = draftByPhoto.get(photo.id);
    const confirmed = confirmedByPhoto.get(photo.id);
    const isPositionLabel = draft?.error_code === 'POSITION_LABEL_DETECTED';
    const labelPositionCode =
      isPositionLabel && draft?.internal_code ? String(draft.internal_code).trim() : '';
    if (labelPositionCode) {
      currentPositionCode = labelPositionCode;
      const parsed = parseDinamicPositionPayload(labelPositionCode);
      if (parsed?.pallet) {
        currentPallet = parsed.pallet;
        currentSide = parsed.side ?? '';
        currentLevel = parsed.level != null ? String(parsed.level) : '';
        currentMarkerIndex = parsed.markerIndex != null ? String(parsed.markerIndex) : '';
        currentMarkerTotal = parsed.markerTotal != null ? String(parsed.markerTotal) : '';
        currentPositionCode = parsed.displayName;
      }
    }

    const positionCode = labelPositionCode
      ? currentPositionCode || labelPositionCode
      : currentPositionCode;
    const positionStatus = labelPositionCode
      ? 'LABEL_DETECTED'
      : currentPositionCode
        ? 'INFERRED_FROM_PRIOR_LABEL'
        : '';

    const requiresReview =
      confirmed == null &&
      (draft == null ||
        draft.status === 'UNRESOLVED' ||
        draft.status === 'AMBIGUOUS' ||
        draft.status === 'FAILED' ||
        draft.status === 'INVALID');
    const source = confirmed
      ? confirmed.source
      : isPositionLabel
        ? 'LOCAL_POSITION_LABEL'
        : draft?.internal_code && !isPositionLabel
          ? 'LOCAL_CODE_SCAN'
          : 'LOCAL_PENDING';

    const productInternalCode = isPositionLabel
      ? ''
      : cell(confirmed?.confirmed_internal_code ?? draft?.internal_code);

    return {
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
      position_code: positionCode,
      position_status: positionStatus,
      pallet: currentPallet,
      side: currentSide,
      level: currentLevel,
      marker_index: currentMarkerIndex,
      marker_total: currentMarkerTotal,
      internal_code: productInternalCode,
      // D1 physical sticker id when present on confirmed/draft; empty for legacy PIPE/DI1.
      label_id: cell(
        isPositionLabel
          ? ''
          : ((confirmed as { label_id?: string | null } | undefined)?.label_id ??
              (draft as { label_id?: string | null } | undefined)?.label_id ??
              ''),
      ),
      quantity: cell(
        isPositionLabel ? null : (confirmed?.confirmed_quantity ?? draft?.quantity),
      ),
      quantity_status: cell(
        isPositionLabel
          ? 'MISSING'
          : (confirmed?.quantity_status ?? draft?.quantity_status),
      ),
      detection_status: cell(confirmed ? 'CONFIRMED' : draft?.status ?? photo.status),
      detector_version: cell(confirmed?.detector_version ?? draft?.detector_version),
      parser_version: cell(confirmed?.parser_version ?? draft?.parser_version),
      prepared_asset_fingerprint: cell(
        confirmed?.prepared_asset_sha256 ?? draft?.prepared_asset_fingerprint,
      ),
      source,
      requires_review: requiresReview ? 'true' : 'false',
      confirmed_manually: confirmed ? 'true' : 'false',
      error_code: cell(draft?.error_code ?? photo.stability_error),
      notes: '',
      freeze_id: cell(input.freezeId ?? input.session.active_freeze_id),
      freeze_generation: cell(input.freezeGeneration ?? input.session.capture_freeze_generation),
    };
  });
}

export async function buildLocalCsvExport(input: LocalCsvExportInput): Promise<LocalCsvExportResult> {
  const rows = buildLocalCsvRows(input);
  assertLocalCsvRowsExportReady(rows);
  const exportId = rows[0]?.export_id ?? input.exportId ?? createId();
  const exportedAt = rows[0]?.exported_at ?? input.exportedAt ?? new Date().toISOString();
  const csv = buildCsvDocument(rows);
  const checksumSha256 = await sha256Hex(csv);
  return {
    exportId,
    exportedAt,
    schemaVersion: LOCAL_CSV_SCHEMA_VERSION,
    rowCount: rows.length,
    checksumSha256,
    checksumAlgorithm: CHECKSUM_ALGORITHM,
    csv,
    scope: 'session',
    freezeId: input.freezeId ?? input.session.active_freeze_id ?? null,
    freezeGeneration: input.freezeGeneration ?? input.session.capture_freeze_generation ?? null,
  };
}
