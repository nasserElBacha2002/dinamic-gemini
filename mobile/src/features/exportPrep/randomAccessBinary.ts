/**
 * Bounded random-access file reads for on-disk ZIP validation.
 * Never loads an entire large ZIP into memory.
 *
 * Android: CaptureForegroundService range/hash APIs.
 * Node/Jest: fs openSync + readSync.
 */

import { base64ToUint8Array } from '../localCsv/binaryCodec';
import { IncrementalSha256 } from './incrementalSha256';
import { ZipWriteError } from './zipWriteError';
import { isNodeRuntime } from './nodeRuntime';
import { requireNodeFs } from './requireNodeFs';
import { resolveNativeRandomAccess } from './captureForegroundNative';


/** Soft cap for a single range read (EOCD scan / small entries / CD slices). */
export const MAX_RANGE_READ_BYTES = 2 * 1024 * 1024;

export interface RandomAccessBinaryFile {
  readonly uri: string;
  size(): Promise<number>;
  readRange(offset: number, length: number): Promise<Uint8Array>;
  /** Streaming SHA-256 of the whole file without retaining it. */
  hashSha256(): Promise<string>;
  close(): Promise<void>;
}

function fileUriToPath(uri: string): string {
  if (uri.startsWith('file://')) {
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
}

type NativeRange = {
  getFileSize: (absolutePath: string) => Promise<number>;
  readFileRangeBase64: (absolutePath: string, offset: number, length: number) => Promise<string>;
  hashFileSha256: (absolutePath: string) => Promise<string>;
};

/**
 * Ensure path is under one of the allowed export roots (sandbox).
 */
export function assertPathInExportSandbox(uri: string, allowedRoots: readonly string[]): void {
  const path = fileUriToPath(uri);
  const normalized = path.replace(/\\/g, '/');
  const ok = allowedRoots.some((root) => {
    const r = fileUriToPath(root).replace(/\\/g, '/').replace(/\/?$/, '/');
    return normalized === r.slice(0, -1) || normalized.startsWith(r);
  });
  if (!ok) {
    throw new ZipWriteError('ZIP_VALIDATION_FAILED', 'path outside export sandbox');
  }
  if (normalized.includes('..')) {
    throw new ZipWriteError('ZIP_VALIDATION_FAILED', 'path traversal rejected');
  }
}

export async function openRandomAccessBinaryFile(
  uri: string,
  options?: { readonly allowedRoots?: readonly string[] },
): Promise<RandomAccessBinaryFile> {
  if (options?.allowedRoots?.length) {
    assertPathInExportSandbox(uri, options.allowedRoots);
  }

  if (isNodeRuntime()) {
    const fs = requireNodeFs();
    const abs = fileUriToPath(uri);
    const fd = fs.openSync(abs, 'r');
    let closed = false;
    return {
      uri,
      async size() {
        return fs.fstatSync(fd).size;
      },
      async readRange(offset: number, length: number) {
        if (closed) throw new Error('file closed');
        if (offset < 0 || length < 0 || length > MAX_RANGE_READ_BYTES) {
          throw new ZipWriteError('ZIP_VALIDATION_FAILED', `bad range ${offset}+${length}`);
        }
        const buf = new Uint8Array(length);
        const n = fs.readSync(fd, buf, 0, length, offset);
        return buf.subarray(0, n);
      },
      async hashSha256() {
        const hasher = new IncrementalSha256();
        const size = fs.fstatSync(fd).size;
        const CHUNK = 64 * 1024;
        let offset = 0;
        while (offset < size) {
          const n = Math.min(CHUNK, size - offset);
          const buf = new Uint8Array(n);
          fs.readSync(fd, buf, 0, n, offset);
          hasher.update(buf);
          offset += n;
        }
        return hasher.digestHex();
      },
      async close() {
        if (!closed) {
          fs.closeSync(fd);
          closed = true;
        }
      },
    };
  }

  const native: NativeRange | null = resolveNativeRandomAccess();
  if (native) {
    const abs = fileUriToPath(uri);
    return {
      uri,
      async size() {
        return Math.trunc(await native.getFileSize(abs));
      },
      async readRange(offset: number, length: number) {
        if (offset < 0 || length < 0 || length > MAX_RANGE_READ_BYTES) {
          throw new ZipWriteError('ZIP_VALIDATION_FAILED', `bad range ${offset}+${length}`);
        }
        const b64 = await native.readFileRangeBase64(abs, offset, length);
        return base64ToUint8Array(b64);
      },
      async hashSha256() {
        return (await native.hashFileSha256(abs)).toLowerCase();
      },
      async close() {
        /* native has no handle */
      },
    };
  }

  throw new ZipWriteError(
    'ZIP_WRITE_FAILED',
    'no random-access file API (Android native / Node). Cannot validate ZIP without loading it whole.',
  );
}
