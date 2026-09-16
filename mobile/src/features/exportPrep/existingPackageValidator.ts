/**
 * Validate an existing on-disk ZIP/CSV before reporting reused=true.
 * Size > 0 alone is never sufficient.
 */

import { unzipSync, strFromU8 } from 'fflate';
import * as FileSystem from 'expo-file-system';

import { sha256BytesHex } from '../../core/payloadFingerprint';
import { base64ToUint8Array } from '../localCsv/binaryCodec';
import type { LocalCsvExportRow } from '../../database/repositories/localCsvExportRepository';

export interface ExistingPackageValidationOk {
  readonly ok: true;
  readonly zipUri: string;
  readonly zipSizeBytes: number;
  readonly zipSha256: string;
}

export interface ExistingPackageValidationFail {
  readonly ok: false;
  readonly reason: string;
}

export type ExistingPackageValidationResult =
  | ExistingPackageValidationOk
  | ExistingPackageValidationFail;

function fail(reason: string): ExistingPackageValidationFail {
  return { ok: false, reason };
}

async function readFileBytes(uri: string): Promise<Uint8Array> {
  const b64 = await FileSystem.readAsStringAsync(uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  return base64ToUint8Array(b64);
}

/**
 * Validate CSV + ZIP on disk against stored integrity fields and expected fingerprint.
 */
export async function validateExistingExportPackage(input: {
  readonly row: LocalCsvExportRow;
  readonly expectedContentFingerprint: string;
  readonly zipUri: string;
}): Promise<ExistingPackageValidationResult> {
  const { row, expectedContentFingerprint, zipUri } = input;
  if (!row.file_uri) {
    return fail('missing_csv_uri');
  }
  if (row.content_fingerprint !== expectedContentFingerprint) {
    return fail('fingerprint_mismatch');
  }

  const csvInfo = await FileSystem.getInfoAsync(row.file_uri);
  if (
    !csvInfo.exists ||
    !('size' in csvInfo) ||
    typeof csvInfo.size !== 'number' ||
    csvInfo.size <= 0
  ) {
    return fail('csv_missing_or_empty');
  }

  const zipInfo = await FileSystem.getInfoAsync(zipUri);
  if (
    !zipInfo.exists ||
    !('size' in zipInfo) ||
    typeof zipInfo.size !== 'number' ||
    zipInfo.size <= 0
  ) {
    return fail('zip_missing_or_empty');
  }
  const zipSize = zipInfo.size;
  if (row.zip_size_bytes != null && row.zip_size_bytes !== zipSize) {
    return fail('zip_size_mismatch');
  }

  let zipBytes: Uint8Array;
  try {
    zipBytes = await readFileBytes(zipUri);
  } catch {
    return fail('zip_unreadable');
  }
  if (zipBytes.byteLength !== zipSize) {
    return fail('zip_read_size_mismatch');
  }

  const zipSha = sha256BytesHex(zipBytes);
  if (row.zip_sha256 != null && row.zip_sha256 !== zipSha) {
    return fail('zip_sha_mismatch');
  }

  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(zipBytes);
  } catch {
    return fail('zip_corrupt');
  }
  if (!entries['results.csv'] || !entries['manifest.json']) {
    return fail('zip_missing_required_entries');
  }

  let manifest: { package_checksum_sha256?: string };
  try {
    const manifestText = strFromU8(entries['manifest.json']);
    manifest = JSON.parse(manifestText) as { package_checksum_sha256?: string };
  } catch {
    return fail('manifest_invalid_json');
  }

  const pkgChecksum =
    manifest.package_checksum_sha256 ?? row.package_checksum_sha256 ?? null;
  if (pkgChecksum != null && pkgChecksum !== expectedContentFingerprint) {
    return fail('manifest_fingerprint_mismatch');
  }
  if (
    row.package_checksum_sha256 != null &&
    row.package_checksum_sha256 !== expectedContentFingerprint
  ) {
    return fail('stored_package_checksum_mismatch');
  }

  return {
    ok: true,
    zipUri,
    zipSizeBytes: zipSize,
    zipSha256: zipSha,
  };
}
