import type { ConfirmedLocalResultRow } from '../../database/repositories/confirmedLocalResultRepository';
import type { AuthoritativeLocalCodeScanRequest } from './authoritativeLocalResultApi';

export function mapConfirmedToAuthoritativeRequest(
  row: ConfirmedLocalResultRow,
): AuthoritativeLocalCodeScanRequest {
  const confirmedCode = (row.confirmed_internal_code || '').trim() || null;
  const base: AuthoritativeLocalCodeScanRequest = {
    schema_version: '1',
    result_id: row.id,
    client_file_id: row.client_file_id!,
    internal_code: confirmedCode,
    quantity: row.confirmed_quantity,
    quantity_status: row.quantity_status,
    source: row.source,
    label_id: row.label_id,
    detected_internal_code: row.detected_internal_code,
    detected_quantity: row.detected_quantity,
    detected_symbology: row.detected_symbology,
    parser_version: row.parser_version,
    detector_version: row.detector_version,
    prepared_asset_sha256: row.prepared_asset_sha256,
    confirmed_at: row.confirmed_at,
  };
  const snapshotRaw = row.recognition_profile_snapshot_json;
  if (!snapshotRaw) return base;
  try {
    const snap = JSON.parse(snapshotRaw) as {
      offline?: boolean;
      item?: {
        profile_source?: string;
        profile_id?: string;
        profile_version?: number;
        configuration_schema_version?: number;
        status?: string;
      };
      client_supplier_id?: string;
    };
    const item = snap.item ?? {};
    const profileSource =
      item.profile_source === 'SUPPLIER' || item.profile_source === 'DINAMIC'
        ? item.profile_source
        : null;
    // Identity-only: never invent internal_code from label_id.
    const internalCode =
      profileSource === 'SUPPLIER' && !confirmedCode && row.label_id
        ? null
        : confirmedCode;
    return {
      ...base,
      internal_code: internalCode,
      profile_source: profileSource,
      profile_id: item.profile_id ?? null,
      profile_version: item.profile_version ?? null,
      configuration_schema_version: item.configuration_schema_version ?? null,
      label_kind: 'ITEM',
      client_supplier_id: snap.client_supplier_id ?? null,
      recognition_status: item.status ?? null,
      captured_offline: snap.offline === true,
    };
  } catch {
    return base;
  }
}
