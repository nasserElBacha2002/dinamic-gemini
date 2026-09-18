/**
 * Bounded-memory ZIP STORE writer (Phase 5).
 *
 * Strategy A (incremental): write local headers + entry bytes + central directory
 * via BinaryAppendSink. Peak ≈ one entry Uint8Array + small framing + CD metadata.
 * Does NOT accumulate all photos or the full ZIP in RAM.
 *
 * JPEG photos use method STORE (0). ZIP64 is rejected (importer / ZIP32 limits).
 */

import { createBinaryAppendSink, type BinaryAppendSink } from './binaryAppendSink';
import { crc32Bytes } from './crc32';
import { digestAbsoluteFile } from './digestAbsoluteFile';
import { sha256BytesHex } from '../../core/payloadFingerprint';
import { isNodeRuntime } from './nodeRuntime';
import { resolveNativeBinaryAppend } from './captureForegroundNative';
import { encodeUtf8 } from './utf8';
import { ZipWriteError, type ZipWriteFailure } from './zipWriteError';

export type { ZipWriteFailure };
export { ZipWriteError };

export type ZipWriteStage =
  | 'PREPARING'
  | 'WRITING_ENTRIES'
  | 'WRITING_DIRECTORY'
  | 'VALIDATING'
  | 'PUBLISHING';

export interface ZipWriteProgress {
  readonly completedEntries: number;
  readonly totalEntries: number;
  readonly processedBytes: number;
  readonly totalBytes: number;
  readonly currentEntry?: string;
  readonly stage: ZipWriteStage;
}

export interface BoundedZipEntry {
  readonly path: string;
  /** Uncompressed size hint (required for ZIP32 planning). */
  readonly sizeBytes: number;
  /**
   * Load entry bytes into JS. Prefer sourceAbsolutePath for large photos
   * (native/Node stream append — no Base64 through the bridge).
   */
  readonly getBytes?: () => Promise<Uint8Array> | Uint8Array;
  /**
   * Absolute filesystem path (or file:// URI) to stream into the ZIP.
   * When set, WRITING_ENTRIES avoids loading the photo into JS.
   */
  readonly sourceAbsolutePath?: string;
  /** When set, bytes must match this SHA-256 or ZIP_SOURCE_CHANGED. */
  readonly expectedSha256?: string;
  /** Optional gate (e.g. freeze check) before streaming/appending this entry. */
  readonly beforeAppend?: () => Promise<void> | void;
}

export interface ZipWriteResult {
  readonly byteLength: number;
  readonly sha256: string;
  readonly entryCount: number;
  readonly method: 'STORE';
  /** Peak simultaneous open entries (must be ≤1 for concurrency=1). */
  readonly peakOpenEntries: number;
  /** Absolute path where bytes were written (Jest may remap documentDirectory). */
  readonly physicalPath: string;
}

/** ZIP32 unsigned 32-bit max (sizes/offsets). */
export const ZIP32_MAX_UINT32 = 0xffffffff;
/** Practical EOCD entry count limit without ZIP64. */
export const ZIP32_MAX_ENTRIES = 0xffff;
/** Default soft cap aligned with LocalCsvExportService (~480 MiB). */
export const DEFAULT_MAX_ZIP_BYTES = 480 * 1024 * 1024;

const SIG_LFH = 0x04034b50;
const SIG_CEN = 0x02014b50;
const SIG_EOCD = 0x06054b50;
const METHOD_STORE = 0;
const VERSION_EXTRACT = 20;
const FLAG_UTF8 = 0x0800;

interface CentralEntry {
  readonly pathBytes: Uint8Array;
  readonly crc32: number;
  readonly size: number;
  readonly localHeaderOffset: number;
}

function encodePath(path: string): Uint8Array {
  if (!path || path.includes('..') || path.startsWith('/') || path.includes('\\')) {
    throw new ZipWriteError('ZIP_VALIDATION_FAILED', `unsafe zip path: ${path}`);
  }
  const bytes = encodeUtf8(path);
  if (bytes.length > 0xffff) {
    throw new ZipWriteError('ZIP_ENTRY_TOO_LARGE', `path too long: ${path.length}`);
  }
  return bytes;
}

function dosDateTime(d = new Date()): { time: number; date: number } {
  const year = Math.max(1980, d.getFullYear());
  const time =
    ((d.getHours() & 0x1f) << 11) |
    ((d.getMinutes() & 0x3f) << 5) |
    ((Math.floor(d.getSeconds() / 2) & 0x1f) >>> 0);
  const date =
    (((year - 1980) & 0x7f) << 9) |
    (((d.getMonth() + 1) & 0x0f) << 5) |
    (d.getDate() & 0x1f);
  return { time, date };
}

function assertAbort(signal: AbortSignal | undefined): void {
  if (signal?.aborted) {
    throw new ZipWriteError('ZIP_CANCELLED', 'abort signal');
  }
}

function emitProgress(
  onProgress: ((p: ZipWriteProgress) => void) | undefined,
  last: { t: number; completed: number },
  progress: ZipWriteProgress,
  force = false,
): void {
  if (!onProgress) return;
  const now = Date.now();
  if (
    !force &&
    now - last.t < 250 &&
    progress.completedEntries === last.completed &&
    progress.stage === 'WRITING_ENTRIES'
  ) {
    return;
  }
  last.t = now;
  last.completed = progress.completedEntries;
  onProgress(progress);
}

/**
 * Write a STORE ZIP incrementally to targetUri (tmp path recommended).
 * Caller owns atomic publish (move) after success.
 */
export async function writeBoundedStoreZip(input: {
  readonly targetUri: string;
  readonly entries: readonly BoundedZipEntry[];
  readonly signal?: AbortSignal;
  readonly onProgress?: (progress: ZipWriteProgress) => void;
  readonly maxTotalBytes?: number;
  /** Optional sink factory (tests). */
  readonly createSink?: (uri: string) => Promise<BinaryAppendSink>;
}): Promise<ZipWriteResult> {
  const maxTotal = input.maxTotalBytes ?? DEFAULT_MAX_ZIP_BYTES;
  const entries = input.entries;
  if (entries.length > ZIP32_MAX_ENTRIES) {
    throw new ZipWriteError(
      'ZIP_TOO_MANY_ENTRIES',
      `${entries.length} > ${ZIP32_MAX_ENTRIES} (ZIP64 unsupported)`,
    );
  }

  let estimated = 0;
  const seenPaths = new Set<string>();
  for (const e of entries) {
    if (seenPaths.has(e.path)) {
      throw new ZipWriteError('ZIP_VALIDATION_FAILED', `duplicate path ${e.path}`);
    }
    seenPaths.add(e.path);
    if (e.sizeBytes < 0 || e.sizeBytes > ZIP32_MAX_UINT32) {
      throw new ZipWriteError('ZIP_ENTRY_TOO_LARGE', `${e.path} size ${e.sizeBytes}`);
    }
    estimated += e.sizeBytes;
  }
  // Rough overhead: LFH(~30+name) + CEN(~46+name) + EOCD(22) per entry ≈ 100 + name
  const overhead = entries.length * 160 + 64;
  if (estimated + overhead > maxTotal) {
    throw new ZipWriteError(
      'ZIP_TOTAL_TOO_LARGE',
      `estimado ${estimated + overhead} > ${maxTotal}`,
    );
  }

  assertAbort(input.signal);
  emitProgress(
    input.onProgress,
    { t: 0, completed: -1 },
    {
      completedEntries: 0,
      totalEntries: entries.length,
      processedBytes: 0,
      totalBytes: estimated,
      stage: 'PREPARING',
    },
    true,
  );

  const createSink = input.createSink ?? createBinaryAppendSink;
  const sink = await createSink(input.targetUri);
  const central: CentralEntry[] = [];
  const { time: dosTime, date: dosDate } = dosDateTime();
  const throttle = { t: 0, completed: -1 };
  let processedBytes = 0;
  let openCount = 0;
  let peakOpenEntries = 0;

  try {
    assertAbort(input.signal);
    for (let i = 0; i < entries.length; i += 1) {
      assertAbort(input.signal);
      const entry = entries[i]!;
      const pathBytes = encodePath(entry.path);
      emitProgress(input.onProgress, throttle, {
        completedEntries: i,
        totalEntries: entries.length,
        processedBytes,
        totalBytes: estimated,
        currentEntry: entry.path,
        stage: 'WRITING_ENTRIES',
      });

      if (entry.beforeAppend) {
        await entry.beforeAppend();
      }

      openCount += 1;
      peakOpenEntries = Math.max(peakOpenEntries, openCount);
      if (openCount > 1) {
        throw new ZipWriteError('ZIP_WRITE_FAILED', 'invariant: >1 entry open');
      }

      let raw: Uint8Array | null = null;
      try {
        let crc: number;
        let payloadSize: number;
        const localOffset = sink.byteLength;
        if (localOffset > ZIP32_MAX_UINT32) {
          throw new ZipWriteError('ZIP_OFFSET_OVERFLOW', `offset ${localOffset}`);
        }

        const sourcePath = entry.sourceAbsolutePath?.trim();
        const appendFromFile = sink.appendFromFile?.bind(sink);
        const canStreamFromFile =
          !!sourcePath &&
          typeof appendFromFile === 'function' &&
          (isNodeRuntime() || !!resolveNativeBinaryAppend()?.appendFile);
        if (canStreamFromFile && sourcePath && appendFromFile) {
          // Fast path: digest + stream-append without loading photo into JS / Base64 bridge.
          let dig;
          try {
            dig = await digestAbsoluteFile(sourcePath);
          } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            throw new ZipWriteError('ZIP_SOURCE_READ_FAILED', `${entry.path}: ${msg}`);
          }
          if (dig.size <= 0) {
            throw new ZipWriteError('ZIP_SOURCE_CHANGED', `${entry.path} empty`);
          }
          if (dig.size !== entry.sizeBytes) {
            throw new ZipWriteError(
              'ZIP_SOURCE_CHANGED',
              `${entry.path} size ${dig.size} != ${entry.sizeBytes}`,
            );
          }
          if (dig.size > ZIP32_MAX_UINT32) {
            throw new ZipWriteError('ZIP_ENTRY_TOO_LARGE', entry.path);
          }
          if (entry.expectedSha256 && dig.sha256 !== entry.expectedSha256.toLowerCase()) {
            throw new ZipWriteError('ZIP_SOURCE_CHANGED', `${entry.path} sha mismatch`);
          }
          crc = dig.crc32 >>> 0;
          payloadSize = dig.size;

          const lfh = new Uint8Array(30 + pathBytes.length);
          const view = new DataView(lfh.buffer);
          view.setUint32(0, SIG_LFH, true);
          view.setUint16(4, VERSION_EXTRACT, true);
          view.setUint16(6, FLAG_UTF8, true);
          view.setUint16(8, METHOD_STORE, true);
          view.setUint16(10, dosTime, true);
          view.setUint16(12, dosDate, true);
          view.setUint32(14, crc, true);
          view.setUint32(18, payloadSize, true);
          view.setUint32(22, payloadSize, true);
          view.setUint16(26, pathBytes.length, true);
          view.setUint16(28, 0, true);
          lfh.set(pathBytes, 30);

          await sink.append(lfh, input.signal);
          const copied = await appendFromFile(sourcePath, input.signal);
          if (copied !== payloadSize) {
            throw new ZipWriteError(
              'ZIP_WRITE_FAILED',
              `${entry.path} appendFromFile copied ${copied} != ${payloadSize}`,
            );
          }
        } else {
          if (!entry.getBytes) {
            throw new ZipWriteError(
              'ZIP_SOURCE_READ_FAILED',
              `${entry.path}: missing getBytes and sourceAbsolutePath`,
            );
          }
          try {
            raw = await entry.getBytes();
          } catch (error) {
            if (
              error instanceof Error &&
              (error.name === 'ExportFromStagingError' || error.name === 'ZipWriteError')
            ) {
              throw error;
            }
            const msg = error instanceof Error ? error.message : String(error);
            throw new ZipWriteError('ZIP_SOURCE_READ_FAILED', `${entry.path}: ${msg}`);
          }

          if (!raw || raw.byteLength === 0) {
            throw new ZipWriteError('ZIP_SOURCE_CHANGED', `${entry.path} empty`);
          }
          if (raw.byteLength !== entry.sizeBytes) {
            throw new ZipWriteError(
              'ZIP_SOURCE_CHANGED',
              `${entry.path} size ${raw.byteLength} != ${entry.sizeBytes}`,
            );
          }
          if (raw.byteLength > ZIP32_MAX_UINT32) {
            throw new ZipWriteError('ZIP_ENTRY_TOO_LARGE', entry.path);
          }
          if (entry.expectedSha256) {
            const sha = sha256BytesHex(raw);
            if (sha !== entry.expectedSha256.toLowerCase()) {
              throw new ZipWriteError('ZIP_SOURCE_CHANGED', `${entry.path} sha mismatch`);
            }
          }

          crc = crc32Bytes(raw);
          payloadSize = raw.byteLength;

          const lfh = new Uint8Array(30 + pathBytes.length);
          const view = new DataView(lfh.buffer);
          view.setUint32(0, SIG_LFH, true);
          view.setUint16(4, VERSION_EXTRACT, true);
          view.setUint16(6, FLAG_UTF8, true);
          view.setUint16(8, METHOD_STORE, true);
          view.setUint16(10, dosTime, true);
          view.setUint16(12, dosDate, true);
          view.setUint32(14, crc, true);
          view.setUint32(18, payloadSize, true);
          view.setUint32(22, payloadSize, true);
          view.setUint16(26, pathBytes.length, true);
          view.setUint16(28, 0, true);
          lfh.set(pathBytes, 30);

          await sink.append(lfh, input.signal);
          await sink.append(raw, input.signal);
        }

        central.push({
          pathBytes,
          crc32: crc,
          size: payloadSize,
          localHeaderOffset: localOffset,
        });
        processedBytes += payloadSize;
      } finally {
        raw = null;
        openCount -= 1;
      }

      emitProgress(
        input.onProgress,
        throttle,
        {
          completedEntries: i + 1,
          totalEntries: entries.length,
          processedBytes,
          totalBytes: estimated,
          currentEntry: entry.path,
          stage: 'WRITING_ENTRIES',
        },
        true,
      );
    }

    assertAbort(input.signal);
    emitProgress(
      input.onProgress,
      throttle,
      {
        completedEntries: entries.length,
        totalEntries: entries.length,
        processedBytes,
        totalBytes: estimated,
        stage: 'WRITING_DIRECTORY',
      },
      true,
    );

    const cdStart = sink.byteLength;
    if (cdStart > ZIP32_MAX_UINT32) {
      throw new ZipWriteError('ZIP_OFFSET_OVERFLOW', `cdStart ${cdStart}`);
    }

    for (const c of central) {
      const cen = new Uint8Array(46 + c.pathBytes.length);
      const view = new DataView(cen.buffer);
      view.setUint32(0, SIG_CEN, true);
      view.setUint16(4, VERSION_EXTRACT, true);
      view.setUint16(6, VERSION_EXTRACT, true);
      view.setUint16(8, FLAG_UTF8, true);
      view.setUint16(10, METHOD_STORE, true);
      view.setUint16(12, dosTime, true);
      view.setUint16(14, dosDate, true);
      view.setUint32(16, c.crc32, true);
      view.setUint32(20, c.size, true);
      view.setUint32(24, c.size, true);
      view.setUint16(28, c.pathBytes.length, true);
      view.setUint16(30, 0, true);
      view.setUint16(32, 0, true);
      view.setUint16(34, 0, true);
      view.setUint16(36, 0, true);
      view.setUint32(38, 0, true);
      view.setUint32(42, c.localHeaderOffset, true);
      cen.set(c.pathBytes, 46);
      await sink.append(cen, input.signal);
    }

    const cdSize = sink.byteLength - cdStart;
    const eocd = new Uint8Array(22);
    const ev = new DataView(eocd.buffer);
    ev.setUint32(0, SIG_EOCD, true);
    ev.setUint16(4, 0, true);
    ev.setUint16(6, 0, true);
    ev.setUint16(8, central.length, true);
    ev.setUint16(10, central.length, true);
    ev.setUint32(12, cdSize, true);
    ev.setUint32(16, cdStart, true);
    ev.setUint16(20, 0, true);
    await sink.append(eocd, input.signal);

    if (sink.byteLength > maxTotal) {
      throw new ZipWriteError(
        'ZIP_TOTAL_TOO_LARGE',
        `final ${sink.byteLength} > ${maxTotal}`,
      );
    }

    emitProgress(
      input.onProgress,
      throttle,
      {
        completedEntries: entries.length,
        totalEntries: entries.length,
        processedBytes,
        totalBytes: estimated,
        stage: 'VALIDATING',
      },
      true,
    );

    await sink.close();
    const sha256 = sink.digestHex();
    return {
      byteLength: sink.byteLength,
      sha256,
      entryCount: central.length,
      method: 'STORE',
      peakOpenEntries,
      physicalPath: sink.physicalPath,
    };
  } catch (error) {
    await sink.close().catch(() => undefined);
    throw error;
  }
}
