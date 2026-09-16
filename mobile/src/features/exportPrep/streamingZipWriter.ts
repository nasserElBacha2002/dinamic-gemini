/**
 * Bounded-memory ZIP builder for local aisle export (Phase 5).
 *
 * Previous fflate Zip path accumulated all ZIP chunks then Base64-encoded the full archive.
 * writeStoreZipAtomic now delegates to writeBoundedStoreZip (STORE + append sink).
 *
 * TECHNICAL NOTE (Expo SDK 51):
 * Disk append uses CaptureForegroundService.appendBase64File on Android, or Node fs in tests.
 * Peak ≈ one photo Uint8Array + framing + Base64 encode of ≤256 KiB append chunks — not Σ(photos)+ZIP.
 */

import * as FileSystem from 'expo-file-system';

import {
  writeBoundedStoreZip,
  ZipWriteError,
  type BoundedZipEntry,
  type ZipWriteProgress,
  type ZipWriteResult,
} from './boundedZipWriter';

export type { BoundedZipEntry, ZipWriteProgress, ZipWriteResult };
export { ZipWriteError, writeBoundedStoreZip } from './boundedZipWriter';

export interface StreamingZipEntry {
  readonly path: string;
  readonly getBytes: () => Promise<Uint8Array> | Uint8Array;
  /** Required — avoids a probe read that would retain bytes. */
  readonly sizeBytes: number;
  readonly expectedSha256?: string;
}

/** @deprecated Prefer writeStoreZipAtomic / writeBoundedStoreZip — in-memory only for tiny probes. */
export async function buildStoreZipBytes(
  entries: readonly Omit<StreamingZipEntry, 'sizeBytes'>[],
): Promise<Uint8Array> {
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
    void (async () => {
      try {
        for (const entry of entries) {
          const bytes = await entry.getBytes();
          const file = new ZipPassThrough(entry.path);
          zip.add(file);
          file.push(bytes, true);
        }
        zip.end();
      } catch (error) {
        reject(error);
      }
    })();
  });
}

/**
 * Build STORE ZIP with bounded memory and publish atomically via tmp + move.
 */
export async function writeStoreZipAtomic(input: {
  readonly entries: readonly StreamingZipEntry[];
  readonly targetUri: string;
  readonly onProgress?: (done: number, total: number) => void;
  readonly onZipProgress?: (progress: ZipWriteProgress) => void;
  readonly signal?: AbortSignal;
  readonly maxTotalBytes?: number;
}): Promise<ZipWriteResult> {
  const dir = input.targetUri.replace(/\/[^/]+$/, '/');
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
  const tmpUri = `${input.targetUri}.tmp.${Date.now()}`;

  const bounded: BoundedZipEntry[] = [];
  for (const e of input.entries) {
    if (e.sizeBytes == null || e.sizeBytes < 0 || !Number.isFinite(e.sizeBytes)) {
      throw new ZipWriteError('ZIP_VALIDATION_FAILED', `missing sizeBytes for ${e.path}`);
    }
    const entry: BoundedZipEntry = {
      path: e.path,
      sizeBytes: e.sizeBytes,
      getBytes: e.getBytes,
      ...(e.expectedSha256 ? { expectedSha256: e.expectedSha256 } : {}),
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
        if (input.onProgress && (p.stage === 'WRITING_ENTRIES' || p.stage === 'PREPARING')) {
          input.onProgress(p.completedEntries, p.totalEntries);
        }
      },
    });
    await FileSystem.deleteAsync(input.targetUri, { idempotent: true }).catch(() => undefined);
    await FileSystem.moveAsync({ from: tmpUri, to: input.targetUri });
    return written;
  } catch (error) {
    await FileSystem.deleteAsync(tmpUri, { idempotent: true }).catch(() => undefined);
    throw error;
  }
}
