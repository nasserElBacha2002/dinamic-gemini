/**
 * On-disk bounded ZIP validator (Phase 5 corrections).
 * Reads EOCD + central directory + small entries via range I/O.
 * Does not load the full archive or photo payloads into RAM (unless verifyCrcAll).
 */

import {
  LOCAL_PACKAGE_KIND,
  LOCAL_PACKAGE_VERSION,
} from '../localCsv/localPackageContract';
import { crc32Update } from './crc32';
import {
  openRandomAccessBinaryFile,
  type RandomAccessBinaryFile,
  MAX_RANGE_READ_BYTES,
} from './randomAccessBinary';
import { decodeUtf8 } from './utf8';

const SIG_LFH = 0x04034b50;
const SIG_CEN = 0x02014b50;
const METHOD_STORE = 0;
const EOCD_MIN = 22;
const EOCD_SCAN_MAX = 0xffff + EOCD_MIN;

export interface OnDiskZipEntryMeta {
  readonly path: string;
  readonly method: number;
  readonly crc32: number;
  readonly compressedSize: number;
  readonly uncompressedSize: number;
  readonly localHeaderOffset: number;
}

export interface OnDiskZipValidationOk {
  readonly ok: true;
  readonly entryCount: number;
  readonly entries: readonly OnDiskZipEntryMeta[];
  readonly zipSizeBytes: number;
  readonly zipSha256: string | null;
  readonly manifest: Record<string, unknown>;
  readonly rangeReads: number;
  readonly maxBufferBytes: number;
}

export interface OnDiskZipValidationFail {
  readonly ok: false;
  readonly reason: string;
}

export type OnDiskZipValidationResult = OnDiskZipValidationOk | OnDiskZipValidationFail;

function fail(reason: string): OnDiskZipValidationFail {
  return { ok: false, reason };
}

function isSafeZipPath(path: string): boolean {
  return Boolean(path) && !path.includes('..') && !path.startsWith('/') && !path.includes('\\');
}

async function findEocdOffset(
  file: RandomAccessBinaryFile,
  size: number,
  stats: { rangeReads: number; maxBuffer: number },
): Promise<number> {
  if (size < EOCD_MIN) return -1;
  const scan = Math.min(size, EOCD_SCAN_MAX);
  const offset = size - scan;
  const buf = await file.readRange(offset, scan);
  stats.rangeReads += 1;
  stats.maxBuffer = Math.max(stats.maxBuffer, buf.byteLength);
  for (let i = buf.byteLength - EOCD_MIN; i >= 0; i -= 1) {
    if (
      buf[i] === 0x50 &&
      buf[i + 1] === 0x4b &&
      buf[i + 2] === 0x05 &&
      buf[i + 3] === 0x06
    ) {
      return offset + i;
    }
  }
  return -1;
}

async function streamCrc32(
  file: RandomAccessBinaryFile,
  offset: number,
  length: number,
  stats: { rangeReads: number; maxBuffer: number },
): Promise<number> {
  let crc = 0;
  let remaining = length;
  let pos = offset;
  const CHUNK = Math.min(64 * 1024, MAX_RANGE_READ_BYTES);
  while (remaining > 0) {
    const n = Math.min(CHUNK, remaining);
    const chunk = await file.readRange(pos, n);
    stats.rangeReads += 1;
    stats.maxBuffer = Math.max(stats.maxBuffer, chunk.byteLength);
    crc = crc32Update(crc, chunk);
    pos += n;
    remaining -= n;
  }
  return crc;
}

export interface ValidateOnDiskStoreZipInput {
  readonly uri: string;
  readonly allowedRoots?: readonly string[];
  /** When set, must match streamed file hash. */
  readonly expectedSha256?: string | null;
  /** When set, must match file size. */
  readonly expectedSizeBytes?: number | null;
  readonly expectedContentFingerprint?: string | null;
  /** Stream-verify CRC for every entry (bounded chunks). Default: csv+manifest only. */
  readonly verifyCrcAll?: boolean;
  /** Compute SHA-256 of the file. Default true when expectedSha256 set. */
  readonly computeSha256?: boolean;
}

/**
 * Validate a STORE ZIP32 package on disk with bounded memory.
 */
export async function validateOnDiskStoreZip(
  input: ValidateOnDiskStoreZipInput,
): Promise<OnDiskZipValidationResult> {
  const stats = { rangeReads: 0, maxBuffer: 0 };
  const file = await openRandomAccessBinaryFile(input.uri, {
    ...(input.allowedRoots ? { allowedRoots: input.allowedRoots } : {}),
  });
  try {
    const size = await file.size();
    if (size <= 0) {
      return fail('zip_empty');
    }
    if (input.expectedSizeBytes != null && input.expectedSizeBytes !== size) {
      return fail('zip_size_mismatch');
    }

    let zipSha256: string | null = null;
    const needHash = input.computeSha256 !== false && (input.expectedSha256 != null || input.computeSha256 === true);
    if (needHash || input.expectedSha256 != null) {
      zipSha256 = await file.hashSha256();
      if (input.expectedSha256 != null && zipSha256 !== input.expectedSha256.toLowerCase()) {
        return fail('zip_sha_mismatch');
      }
    }

    const eocdOff = await findEocdOffset(file, size, stats);
    if (eocdOff < 0) {
      return fail('eocd_missing');
    }
    const eocd = await file.readRange(eocdOff, Math.min(EOCD_MIN + 8, size - eocdOff));
    stats.rangeReads += 1;
    stats.maxBuffer = Math.max(stats.maxBuffer, eocd.byteLength);
    if (eocd.byteLength < EOCD_MIN) {
      return fail('eocd_truncated');
    }
    const ev = new DataView(eocd.buffer, eocd.byteOffset, eocd.byteLength);
    const diskEntries = ev.getUint16(8, true);
    const totalEntries = ev.getUint16(10, true);
    const cdSize = ev.getUint32(12, true);
    const cdOffset = ev.getUint32(16, true);
    if (diskEntries !== totalEntries) {
      return fail('eocd_disk_mismatch');
    }
    if (cdOffset === 0xffffffff || cdSize === 0xffffffff || totalEntries === 0xffff) {
      return fail('zip64_not_supported');
    }
    if (cdOffset + cdSize > size || cdOffset > eocdOff) {
      return fail('cd_out_of_range');
    }
    if (cdSize > MAX_RANGE_READ_BYTES) {
      return fail('cd_too_large_for_bounded_read');
    }

    const cd = await file.readRange(cdOffset, cdSize);
    stats.rangeReads += 1;
    stats.maxBuffer = Math.max(stats.maxBuffer, cd.byteLength);
    const cv = new DataView(cd.buffer, cd.byteOffset, cd.byteLength);

    const entries: OnDiskZipEntryMeta[] = [];
    const seen = new Set<string>();
    let cursor = 0;
    for (let i = 0; i < totalEntries; i += 1) {
      if (cursor + 46 > cd.byteLength) {
        return fail('cen_truncated');
      }
      if (cv.getUint32(cursor, true) !== SIG_CEN) {
        return fail(`cen_bad_sig_${i}`);
      }
      const method = cv.getUint16(cursor + 10, true);
      const crc = cv.getUint32(cursor + 16, true);
      const compSize = cv.getUint32(cursor + 20, true);
      const uncompSize = cv.getUint32(cursor + 24, true);
      const nameLen = cv.getUint16(cursor + 28, true);
      const extraLen = cv.getUint16(cursor + 30, true);
      const commentLen = cv.getUint16(cursor + 32, true);
      const localOff = cv.getUint32(cursor + 42, true);
      const nameStart = cursor + 46;
      const nameEnd = nameStart + nameLen;
      if (nameEnd > cd.byteLength) {
        return fail('cen_name_oob');
      }
      const path = decodeUtf8(cd.subarray(nameStart, nameEnd));
      if (!isSafeZipPath(path)) {
        return fail(`unsafe_path_${path}`);
      }
      if (seen.has(path)) {
        return fail(`duplicate_${path}`);
      }
      seen.add(path);
      if (method !== METHOD_STORE) {
        return fail(`not_store_${path}`);
      }
      if (compSize !== uncompSize) {
        return fail(`store_size_mismatch_${path}`);
      }

      // Local file header consistency (header only — not photo payload).
      const lfhLen = 30;
      if (localOff + lfhLen > size) {
        return fail(`lfh_oob_${path}`);
      }
      const lfh = await file.readRange(localOff, lfhLen);
      stats.rangeReads += 1;
      stats.maxBuffer = Math.max(stats.maxBuffer, lfh.byteLength);
      const lv = new DataView(lfh.buffer, lfh.byteOffset, lfh.byteLength);
      if (lv.getUint32(0, true) !== SIG_LFH) {
        return fail(`lfh_bad_sig_${path}`);
      }
      if (lv.getUint16(8, true) !== METHOD_STORE) {
        return fail(`lfh_not_store_${path}`);
      }
      if (lv.getUint32(14, true) !== crc) {
        return fail(`lfh_crc_mismatch_${path}`);
      }
      if (lv.getUint32(18, true) !== compSize || lv.getUint32(22, true) !== uncompSize) {
        return fail(`lfh_size_mismatch_${path}`);
      }
      const lfhNameLen = lv.getUint16(26, true);
      const lfhExtraLen = lv.getUint16(28, true);
      if (lfhNameLen !== nameLen) {
        return fail(`lfh_name_len_mismatch_${path}`);
      }
      const dataStart = localOff + 30 + lfhNameLen + lfhExtraLen;
      if (dataStart + compSize > size) {
        return fail(`data_oob_${path}`);
      }

      entries.push({
        path,
        method,
        crc32: crc,
        compressedSize: compSize,
        uncompressedSize: uncompSize,
        localHeaderOffset: localOff,
      });
      cursor = nameEnd + extraLen + commentLen;
    }

    if (entries.length !== totalEntries) {
      return fail('entry_count_mismatch');
    }

    const byPath = new Map(entries.map((e) => [e.path, e]));
    if (!byPath.has('results.csv')) {
      return fail('missing_results_csv');
    }
    if (!byPath.has('manifest.json')) {
      return fail('missing_manifest_json');
    }

    const readSmallEntry = async (path: string): Promise<Uint8Array | OnDiskZipValidationFail> => {
      const meta = byPath.get(path)!;
      if (meta.compressedSize > MAX_RANGE_READ_BYTES) {
        return fail(`entry_too_large_${path}`);
      }
      const lfh = await file.readRange(meta.localHeaderOffset, 30);
      stats.rangeReads += 1;
      const lv = new DataView(lfh.buffer, lfh.byteOffset, lfh.byteLength);
      const nameLen = lv.getUint16(26, true);
      const extraLen = lv.getUint16(28, true);
      const dataStart = meta.localHeaderOffset + 30 + nameLen + extraLen;
      const data = await file.readRange(dataStart, meta.compressedSize);
      stats.rangeReads += 1;
      stats.maxBuffer = Math.max(stats.maxBuffer, data.byteLength);
      const crc = crc32Update(0, data);
      if (crc !== meta.crc32) {
        return fail(`crc_mismatch_${path}`);
      }
      return data;
    };

    const csvBytes = await readSmallEntry('results.csv');
    if (!(csvBytes instanceof Uint8Array)) {
      return csvBytes;
    }
    const manifestBytes = await readSmallEntry('manifest.json');
    if (!(manifestBytes instanceof Uint8Array)) {
      return manifestBytes;
    }

    let manifest: Record<string, unknown>;
    try {
      manifest = JSON.parse(decodeUtf8(manifestBytes)) as Record<string, unknown>;
    } catch {
      return fail('manifest_invalid_json');
    }

    if (manifest.package_kind !== LOCAL_PACKAGE_KIND) {
      return fail('package_kind_mismatch');
    }
    if (
      typeof manifest.package_version === 'number' &&
      manifest.package_version !== LOCAL_PACKAGE_VERSION
    ) {
      return fail('package_version_mismatch');
    }

    let photoCount = 0;
    for (const e of entries) {
      if (e.path.startsWith('photos/')) {
        photoCount += 1;
        if (e.uncompressedSize <= 0) {
          return fail(`empty_photo_${e.path}`);
        }
      }
    }

    const included = manifest.included_photo_count;
    const expected = manifest.expected_photo_count;
    if (typeof included === 'number' && included !== photoCount) {
      return fail('manifest_photo_count_mismatch');
    }
    if (typeof expected === 'number' && typeof included === 'number' && expected !== included) {
      return fail('expected_included_mismatch');
    }

    if (input.expectedContentFingerprint != null) {
      const pkg =
        (typeof manifest.package_checksum_sha256 === 'string'
          ? manifest.package_checksum_sha256
          : null) ?? null;
      if (pkg != null && pkg !== input.expectedContentFingerprint) {
        return fail('manifest_fingerprint_mismatch');
      }
    }

    const verifyAll = input.verifyCrcAll === true;
    for (const e of entries) {
      if (e.path === 'results.csv' || e.path === 'manifest.json') {
        continue;
      }
      if (!verifyAll && e.path.startsWith('photos/')) {
        continue;
      }
      const lfh = await file.readRange(e.localHeaderOffset, 30);
      stats.rangeReads += 1;
      const lv = new DataView(lfh.buffer, lfh.byteOffset, lfh.byteLength);
      const nameLen = lv.getUint16(26, true);
      const extraLen = lv.getUint16(28, true);
      const dataStart = e.localHeaderOffset + 30 + nameLen + extraLen;
      const crc = await streamCrc32(file, dataStart, e.compressedSize, stats);
      if (crc !== e.crc32) {
        return fail(`crc_mismatch_${e.path}`);
      }
    }

    return {
      ok: true,
      entryCount: entries.length,
      entries,
      zipSizeBytes: size,
      zipSha256,
      manifest,
      rangeReads: stats.rangeReads,
      maxBufferBytes: stats.maxBuffer,
    };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    if (msg.includes('ZIP_VALIDATION_FAILED') || msg.includes('path outside')) {
      return fail(msg);
    }
    return fail(`zip_validate_error:${msg}`);
  } finally {
    await file.close().catch(() => undefined);
  }
}
