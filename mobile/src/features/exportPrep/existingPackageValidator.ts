/**
 * Validate an existing on-disk ZIP/CSV before reporting reused=true.
 * Uses bounded on-disk ZIP validation — never loads the full ZIP or photo payloads.
 */

import * as FileSystem from 'expo-file-system';

import type { LocalCsvExportRow } from '../../database/repositories/localCsvExportRepository';
import { validateOnDiskStoreZip } from './boundedOnDiskZipValidator';
import { getNodeProcess } from './nodeRuntime';

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

function exportSandboxRoots(): string[] {
  const roots: string[] = [];
  if (FileSystem.documentDirectory) roots.push(FileSystem.documentDirectory);
  if (FileSystem.cacheDirectory) roots.push(FileSystem.cacheDirectory);
  // Jest / Node tmp fallbacks used by binary append sink.
  const tmpdir = getNodeProcess()?.env?.TMPDIR;
  if (tmpdir) {
    roots.push(tmpdir);
  }
  roots.push('/tmp');
  return roots;
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

  const validated = await validateOnDiskStoreZip({
    uri: zipUri,
    allowedRoots: exportSandboxRoots(),
    expectedSizeBytes: row.zip_size_bytes ?? zipInfo.size,
    expectedSha256: row.zip_sha256 ?? null,
    expectedContentFingerprint,
    computeSha256: true,
    verifyCrcAll: false,
  });

  if (!validated.ok) {
    return fail(validated.reason);
  }

  if (
    row.package_checksum_sha256 != null &&
    row.package_checksum_sha256 !== expectedContentFingerprint
  ) {
    return fail('stored_package_checksum_mismatch');
  }

  if (!validated.zipSha256) {
    return fail('zip_sha_missing');
  }

  return {
    ok: true,
    zipUri,
    zipSizeBytes: validated.zipSizeBytes,
    zipSha256: validated.zipSha256,
  };
}
