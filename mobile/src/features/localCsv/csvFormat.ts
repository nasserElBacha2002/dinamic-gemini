/**
 * RFC 4180 CSV helpers for local export/import (UTF-8, formula-safe).
 *
 * Contract notes (schema v1 / v1.1):
 * - `source` = detection provenance (LOCAL_CODE_SCAN, LOCAL_PENDING, …)
 * - Server assigns ingestion_source=LOCAL_CSV_IMPORT; clients must not declare it as `source`
 * - Extra headers (company_id, …) are allowed; backend required set is a subset
 * - Schema 1.1 adds optional `label_id` (D1 physical sticker; empty for legacy PIPE/DI1)
 */

import { sha256Hex as realSha256Hex } from '../../core/payloadFingerprint';

export const LOCAL_CSV_SCHEMA_VERSION = '1.1';

export const LOCAL_CSV_HEADERS = [
  'schema_version',
  'export_id',
  'exported_at',
  'device_id',
  'company_id',
  'client_id',
  'inventory_id',
  'inventory_name',
  'aisle_id',
  'aisle_code',
  'capture_session_id',
  'capture_photo_id',
  'client_file_id',
  'capture_order',
  'captured_at',
  'position_code',
  'position_status',
  'pallet',
  'side',
  'level',
  'marker_index',
  'marker_total',
  'internal_code',
  'label_id',
  'quantity',
  'quantity_status',
  'detection_status',
  'detector_version',
  'parser_version',
  'prepared_asset_fingerprint',
  'source',
  'requires_review',
  'confirmed_manually',
  'error_code',
  'notes',
  'freeze_id',
  'freeze_generation',
] as const;

export type LocalCsvHeader = (typeof LOCAL_CSV_HEADERS)[number];

export type LocalCsvRow = Record<LocalCsvHeader, string>;

/** Detection sources accepted by backend parser (CSV column `source`). */
export const LOCAL_CSV_DETECTION_SOURCES = [
  'LOCAL_PENDING',
  'LOCAL_CODE_SCAN',
  'LOCAL_MANUAL',
  'LOCAL_MANUAL_CORRECTION',
  'LOCAL_POSITION_LABEL',
  'LOCAL_CODE_SCAN_SHADOW',
] as const;

export type LocalCsvDetectionSource = (typeof LOCAL_CSV_DETECTION_SOURCES)[number];

/** Neutralize CSV injection for spreadsheet consumers; reversible on import by stripping prefix. */
export function neutralizeCsvFormula(value: string): string {
  if (value.length === 0) {
    return value;
  }
  const first = value[0]!;
  if (first === '=' || first === '+' || first === '-' || first === '@' || first === '\t' || first === '\r') {
    return `'${value}`;
  }
  return value;
}

export function escapeCsvField(raw: string | null | undefined): string {
  const value = neutralizeCsvFormula(raw == null ? '' : String(raw));
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function buildCsvDocument(rows: readonly LocalCsvRow[]): string {
  const lines: string[] = [LOCAL_CSV_HEADERS.join(',')];
  for (const row of rows) {
    lines.push(LOCAL_CSV_HEADERS.map((h) => escapeCsvField(row[h])).join(','));
  }
  return `${lines.join('\n')}\n`;
}

/** Real SHA-256 hex (same algorithm as payload fingerprints). */
export async function sha256Hex(text: string): Promise<string> {
  return realSha256Hex(text);
}

export const CHECKSUM_ALGORITHM = 'sha256' as const;
