/**
 * Bounded-memory ZIP builder for local aisle export (Phase 5).
 *
 * writeStoreZipAtomic delegates to writeBoundedStoreZip (STORE + append sink).
 * Disk append: CaptureForegroundService on Android, Node fs in tests.
 */

import * as FileSystem from 'expo-file-system';

import {
  writeBoundedStoreZip,
  ZipWriteError,
  type BoundedZipEntry,
  type ZipWriteProgress,
  type ZipWriteResult,
} from './boundedZipWriter';
import { assertZipWritePlatformSupported } from './zipWritePlatform';

export type { BoundedZipEntry, ZipWriteProgress, ZipWriteResult };
export { ZipWriteError, writeBoundedStoreZip } from './boundedZipWriter';

export interface StreamingZipEntry {
  readonly path: string;
  readonly getBytes?: () => Promise<Uint8Array> | Uint8Array;
  /** Stream from disk (photos) — preferred over getBytes on device. */
  readonly sourceAbsolutePath?: string;
  /** Required — avoids a probe read that would retain bytes. */
  readonly sizeBytes: number;
  readonly expectedSha256?: string;
  readonly beforeAppend?: () => Promise<void> | void;
}

/** Hard cap for the deprecated in-memory probe helper (not for photos). */
export const BUILD_STORE_ZIP_BYTES_MAX = 64 * 1024;

/**
 * @deprecated Test/probe only — accumulates the whole ZIP in RAM.
 * Throws if estimated payload exceeds BUILD_STORE_ZIP_BYTES_MAX.
 */
export async function buildStoreZipBytes(
  entries: readonly Omit<StreamingZipEntry, 'sizeBytes'>[],
): Promise<Uint8Array> {
  const materialized: { path: string; bytes: Uint8Array }[] = [];
  let estimated = 0;
  for (const entry of entries) {
    if (!entry.getBytes) {
      throw new ZipWriteError(
        'ZIP_VALIDATION_FAILED',
        `buildStoreZipBytes requires getBytes for ${entry.path}`,
      );
    }
    const bytes = await entry.getBytes();
    estimated += bytes.byteLength;
    if (estimated > BUILD_STORE_ZIP_BYTES_MAX) {
      throw new ZipWriteError(
        'ZIP_TOTAL_TOO_LARGE',
        `buildStoreZipBytes is probe-only (max ${BUILD_STORE_ZIP_BYTES_MAX} bytes); use writeBoundedStoreZip`,
      );
    }
    materialized.push({ path: entry.path, bytes });
  }
  const { Zip, ZipPassThrough } = await import('fflate');
  return new Promise((resolve, reject) => {
    const chunks: Uint8Array[] = [];
    let total = 0;
    const zip = new Zip((err, chunk, final) => {
      if (err) {
        reject(err);
        return;
      }
      if (chunk && chunk.length) {
        chunks.push(chunk);
        total += chunk.length;
      }
      if (final) {
        const out = new Uint8Array(total);
        let offset = 0;
        for (const c of chunks) {
          out.set(c, offset);
          offset += c.length;
        }
        resolve(out);
      }
    });
    try {
      for (const entry of materialized) {
        const file = new ZipPassThrough(entry.path);
        zip.add(file);
        file.push(entry.bytes, true);
      }
      zip.end();
    } catch (error) {
      reject(error);
    }
  });
}

/**
 * Legacy progress adapter: never reports done===total during WRITING_ENTRIES.
 * Callers must report final completion after persist.
 */
export function adaptLegacyZipEntryProgress(
  progress: ZipWriteProgress,
  onProgress: (done: number, total: number) => void,
): void {
  if (progress.stage === 'PREPARING') {
    onProgress(0, Math.max(1, progress.totalEntries));
    return;
  }
  if (progress.stage === 'WRITING_ENTRIES') {
    const total = Math.max(1, progress.totalEntries);
    // Cap at total-1 so UI cannot show 100% before CD/validate/publish.
    const done =
      progress.totalEntries <= 0
        ? 0
        : Math.min(progress.completedEntries, Math.max(0, total - 1));
    onProgress(done, total);
  }
  // WRITING_DIRECTORY / VALIDATING / PUBLISHING: no false 100% via entry counts.
}

/**
 * Build STORE ZIP with bounded memory and publish atomically via tmp + move.
 * Caller should validate on-disk before treating the target as publishable when
 * target is a temp path in the export orchestrator.
 *
 * physicalPath always refers to the final target after move (not the nested
 * `.tmp.<timestamp>` sink path), so native getFileSize/hash see the real file.
 */
export async function writeStoreZipAtomic(input: {
  readonly entries: readonly StreamingZipEntry[];
  readonly targetUri: string;
  readonly onProgress?: (done: number, total: number) => void;
  readonly onZipProgress?: (progress: ZipWriteProgress) => void;
  readonly signal?: AbortSignal;
  readonly maxTotalBytes?: number;
}): Promise<ZipWriteResult> {
  assertZipWritePlatformSupported();
  const dir = input.targetUri.replace(/\/[^/]+$/, '/');
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
  const tmpUri = `${input.targetUri}.tmp.${Date.now()}`;

  const bounded: BoundedZipEntry[] = [];
  for (const e of input.entries) {
    if (e.sizeBytes == null || e.sizeBytes < 0 || !Number.isFinite(e.sizeBytes)) {
      throw new ZipWriteError('ZIP_VALIDATION_FAILED', `missing sizeBytes for ${e.path}`);
    }
    if (!e.sourceAbsolutePath && !e.getBytes) {
      throw new ZipWriteError(
        'ZIP_VALIDATION_FAILED',
        `missing getBytes/sourceAbsolutePath for ${e.path}`,
      );
    }
    const entry: BoundedZipEntry = {
      path: e.path,
      sizeBytes: e.sizeBytes,
      ...(e.getBytes ? { getBytes: e.getBytes } : {}),
      ...(e.sourceAbsolutePath ? { sourceAbsolutePath: e.sourceAbsolutePath } : {}),
      ...(e.expectedSha256 ? { expectedSha256: e.expectedSha256 } : {}),
      ...(e.beforeAppend ? { beforeAppend: e.beforeAppend } : {}),
    };
    bounded.push(entry);
  }

  try {
    const written = await writeBoundedStoreZip({
      targetUri: tmpUri,
      entries: bounded,
      ...(input.signal ? { signal: input.signal } : {}),
      ...(input.maxTotalBytes != null ? { maxTotalBytes: input.maxTotalBytes } : {}),
      onProgress: (p) => {
        input.onZipProgress?.(p);
        if (input.onProgress) {
          adaptLegacyZipEntryProgress(p, input.onProgress);
        }
      },
    });
    await FileSystem.deleteAsync(input.targetUri, { idempotent: true }).catch(() => undefined);
    await FileSystem.moveAsync({ from: tmpUri, to: input.targetUri });
    return {
      ...written,
      physicalPath: fileUriToAbsolutePath(input.targetUri),
    };
  } catch (error) {
    await FileSystem.deleteAsync(tmpUri, { idempotent: true }).catch(() => undefined);
    throw error;
  }
}

function fileUriToAbsolutePath(uri: string): string {
  if (uri.startsWith('file://')) {
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
}
