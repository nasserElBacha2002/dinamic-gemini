import type { ConfirmedLocalResultRow } from '../../database/repositories/confirmedLocalResultRepository';
import type { AuthoritativeLocalCodeScanRequest } from './authoritativeLocalResultApi';

export function mapConfirmedToAuthoritativeRequest(
  row: ConfirmedLocalResultRow,
): AuthoritativeLocalCodeScanRequest {
  return {
    schema_version: '1',
    result_id: row.id,
    client_file_id: row.client_file_id!,
    internal_code: row.confirmed_internal_code,
    quantity: row.confirmed_quantity,
    quantity_status: row.quantity_status,
    source: row.source,
    detected_internal_code: row.detected_internal_code,
    detected_quantity: row.detected_quantity,
    detected_symbology: row.detected_symbology,
    parser_version: row.parser_version,
    detector_version: row.detector_version,
    prepared_asset_sha256: row.prepared_asset_sha256,
    confirmed_at: row.confirmed_at,
  };
}
