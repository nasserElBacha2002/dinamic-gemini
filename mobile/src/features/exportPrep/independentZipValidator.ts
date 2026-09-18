/**
 * Independent STORE ZIP structure validator (Phase 5).
 * Hand-parses LFH / central directory / EOCD — does not share code with boundedZipWriter.
 * Used to verify packages produced by the writer without circular trust.
 */

import { crc32Bytes } from './crc32';
import {
  LOCAL_PACKAGE_KIND,
  LOCAL_PACKAGE_VERSION,
} from '../localCsv/localPackageContract';
import { decodeUtf8 } from './utf8';

const SIG_LFH = 0x04034b50;
const SIG_CEN = 0x02014b50;
const METHOD_STORE = 0;

export interface IndependentZipEntry {
  readonly path: string;
  readonly method: number;
  readonly crc32: number;
  readonly compressedSize: number;
  readonly uncompressedSize: number;
  readonly localHeaderOffset: number;
  readonly data: Uint8Array;
}

export interface IndependentZipParseOk {
  readonly ok: true;
  readonly entries: readonly IndependentZipEntry[];
  readonly entryCount: number;
}

export interface IndependentZipParseFail {
  readonly ok: false;
  readonly reason: string;
}

export type IndependentZipParseResult = IndependentZipParseOk | IndependentZipParseFail;

function fail(reason: string): IndependentZipParseFail {
  return { ok: false, reason };
}

function findEocd(bytes: Uint8Array): number {
  // EOCD is 22+ bytes at end; comment length at offset 20.
  const min = 22;
  if (bytes.length < min) return -1;
  const maxScan = Math.min(bytes.length - min, 0xffff + 22);
  for (let i = bytes.length - min; i >= bytes.length - min - maxScan && i >= 0; i -= 1) {
    if (
      bytes[i] === 0x50 &&
      bytes[i + 1] === 0x4b &&
      bytes[i + 2] === 0x05 &&
      bytes[i + 3] === 0x06
    ) {
      return i;
    }
  }
  return -1;
}

function decodePath(bytes: Uint8Array): string {
  return decodeUtf8(bytes);
}

/**
 * Parse a ZIP32 STORE archive and verify CRC32 of each entry's payload.
 */
export function parseStoreZipIndependent(bytes: Uint8Array): IndependentZipParseResult {
  if (bytes.length < 22) {
    return fail('too_short');
  }
  const eocdOff = findEocd(bytes);
  if (eocdOff < 0) {
    return fail('eocd_missing');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const diskEntries = view.getUint16(eocdOff + 8, true);
  const totalEntries = view.getUint16(eocdOff + 10, true);
  const cdSize = view.getUint32(eocdOff + 12, true);
  const cdOffset = view.getUint32(eocdOff + 16, true);
  if (diskEntries !== totalEntries) {
    return fail('eocd_disk_mismatch');
  }
  if (cdOffset + cdSize > bytes.length) {
    return fail('cd_out_of_range');
  }
  if (cdOffset === 0xffffffff || cdSize === 0xffffffff || totalEntries === 0xffff) {
    return fail('zip64_not_supported');
  }

  const entries: IndependentZipEntry[] = [];
  const seen = new Set<string>();
  let cursor = cdOffset;
  for (let i = 0; i < totalEntries; i += 1) {
    if (cursor + 46 > bytes.length) {
      return fail('cen_truncated');
    }
    const sig = view.getUint32(cursor, true);
    if (sig !== SIG_CEN) {
      return fail(`cen_bad_sig_${i}`);
    }
    const method = view.getUint16(cursor + 10, true);
    const crc = view.getUint32(cursor + 16, true);
    const compSize = view.getUint32(cursor + 20, true);
    const uncompSize = view.getUint32(cursor + 24, true);
    const nameLen = view.getUint16(cursor + 28, true);
    const extraLen = view.getUint16(cursor + 30, true);
    const commentLen = view.getUint16(cursor + 32, true);
    const localOff = view.getUint32(cursor + 42, true);
    const nameStart = cursor + 46;
    const nameEnd = nameStart + nameLen;
    if (nameEnd > bytes.length) {
      return fail('cen_name_oob');
    }
    const path = decodePath(bytes.subarray(nameStart, nameEnd));
    if (!path || path.includes('..') || path.startsWith('/') || path.includes('\\')) {
      return fail(`unsafe_path_${path}`);
    }
    if (seen.has(path)) {
      return fail(`duplicate_${path}`);
    }
    seen.add(path);

    if (localOff + 30 > bytes.length) {
      return fail(`lfh_oob_${path}`);
    }
    const lfhSig = view.getUint32(localOff, true);
    if (lfhSig !== SIG_LFH) {
      return fail(`lfh_bad_sig_${path}`);
    }
    const lfhMethod = view.getUint16(localOff + 8, true);
    const lfhNameLen = view.getUint16(localOff + 26, true);
    const lfhExtraLen = view.getUint16(localOff + 28, true);
    const dataStart = localOff + 30 + lfhNameLen + lfhExtraLen;
    const dataEnd = dataStart + compSize;
    if (dataEnd > bytes.length) {
      return fail(`data_oob_${path}`);
    }
    if (method !== METHOD_STORE || lfhMethod !== METHOD_STORE) {
      return fail(`not_store_${path}`);
    }
    if (compSize !== uncompSize) {
      return fail(`store_size_mismatch_${path}`);
    }
    const data = bytes.subarray(dataStart, dataEnd);
    const actualCrc = crc32Bytes(data);
    if (actualCrc !== crc) {
      return fail(`crc_mismatch_${path}`);
    }
    entries.push({
      path,
      method,
      crc32: crc,
      compressedSize: compSize,
      uncompressedSize: uncompSize,
      localHeaderOffset: localOff,
      data,
    });
    cursor = nameEnd + extraLen + commentLen;
  }

  if (entries.length !== totalEntries) {
    return fail('entry_count_mismatch');
  }

  return { ok: true, entries, entryCount: entries.length };
}

/**
 * Contractual check for local aisle export packages (in-memory — tests / tiny ZIPs only).
 * Production validation uses validateOnDiskStoreZip.
 */
export function validateLocalExportZipContract(bytes: Uint8Array): IndependentZipParseResult {
  const parsed = parseStoreZipIndependent(bytes);
  if (!parsed.ok) {
    return parsed;
  }
  const byPath = new Map(parsed.entries.map((e) => [e.path, e]));
  if (!byPath.has('results.csv')) {
    return fail('missing_results_csv');
  }
  if (!byPath.has('manifest.json')) {
    return fail('missing_manifest_json');
  }
  let photoCount = 0;
  for (const e of parsed.entries) {
    if (e.path.startsWith('photos/')) {
      photoCount += 1;
      if (e.data.byteLength === 0) {
        return fail(`empty_photo_${e.path}`);
      }
    }
  }
  try {
    const manifestText = decodePath(byPath.get('manifest.json')!.data);
    const manifest = JSON.parse(manifestText) as {
      included_photo_count?: number;
      expected_photo_count?: number;
      package_kind?: string;
      package_version?: number;
    };
    if (manifest.package_kind !== LOCAL_PACKAGE_KIND) {
      return fail('package_kind_mismatch');
    }
    if (
      typeof manifest.package_version === 'number' &&
      manifest.package_version !== LOCAL_PACKAGE_VERSION
    ) {
      return fail('package_version_mismatch');
    }
    if (
      typeof manifest.included_photo_count === 'number' &&
      manifest.included_photo_count !== photoCount
    ) {
      return fail('manifest_photo_count_mismatch');
    }
    if (
      typeof manifest.expected_photo_count === 'number' &&
      typeof manifest.included_photo_count === 'number' &&
      manifest.expected_photo_count !== manifest.included_photo_count
    ) {
      return fail('expected_included_mismatch');
    }
  } catch {
    return fail('manifest_invalid_json');
  }
  return parsed;
}
