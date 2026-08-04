/**
 * RFC 4180 CSV helpers for local export/import (UTF-8, formula-safe).
 */

export const LOCAL_CSV_SCHEMA_VERSION = '1';

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
  'internal_code',
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
] as const;

export type LocalCsvHeader = (typeof LOCAL_CSV_HEADERS)[number];

export type LocalCsvRow = Record<LocalCsvHeader, string>;

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

export async function sha256Hex(text: string): Promise<string> {
  // Prefer Web Crypto when available (Hermes / modern RN); fall back to FNV-1a for tests/Node without subtle.
  const subtle = globalThis.crypto?.subtle;
  if (subtle) {
    const data = new TextEncoder().encode(text);
    const digest = await subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a32_${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
