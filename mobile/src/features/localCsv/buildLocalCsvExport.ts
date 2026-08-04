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

  return eligible.map((photo) => {
    const draft = draftByPhoto.get(photo.id);
    const confirmed = confirmedByPhoto.get(photo.id);
    const requiresReview =
      confirmed == null &&
      (draft == null ||
        draft.status === 'UNRESOLVED' ||
        draft.status === 'AMBIGUOUS' ||
        draft.status === 'FAILED' ||
        draft.status === 'INVALID');
    const source = confirmed
      ? confirmed.source
      : draft?.internal_code
        ? 'LOCAL_CODE_SCAN'
        : 'LOCAL_PENDING';

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
      position_code: '',
      position_status: '',
      internal_code: cell(confirmed?.confirmed_internal_code ?? draft?.internal_code),
      quantity: cell(confirmed?.confirmed_quantity ?? draft?.quantity),
      quantity_status: cell(confirmed?.quantity_status ?? draft?.quantity_status),
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
