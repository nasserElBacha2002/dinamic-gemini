/**
 * Binary append sink for bounded ZIP writes.
 *
 * Expo FileSystem (SDK 51 / ~17) cannot append binary without loading the whole file.
 * On Android:
 *   - small framing (LFH/CEN/EOCD): appendBase64File
 *   - photo payloads: appendFile (raw stream copy — no Base64)
 *   - ZIP digest: MessageDigest via hashFileSha256 after close (disk-authoritative)
 * In Node/Jest: fs append + IncrementalSha256.
 */

import * as FileSystem from 'expo-file-system';

import { IncrementalSha256 } from './incrementalSha256';
import { ZipWriteError } from './zipWriteError';
import { isNodeRuntime, nodeTmpDir } from './nodeRuntime';
import { requireNodeFs } from './requireNodeFs';
import {
  missingNativeZipIoDetail,
  resolveNativeBinaryAppend,
  resolveNativeRandomAccess,
  type CaptureForegroundAppendNative,
} from './captureForegroundNative';

export interface BinaryAppendSink {
  readonly uri: string;
  /** Absolute filesystem path used for I/O (may differ from uri under Jest stubs). */
  readonly physicalPath: string;
  append(bytes: Uint8Array, signal?: AbortSignal): Promise<void>;
  /**
   * Append an on-disk file without loading it into JS (Android native / Node fs).
   * Prefer this for photo payloads.
   */
  appendFromFile?(sourceAbsolutePath: string, signal?: AbortSignal): Promise<number>;
  /** Bytes written so far (uncompressed ZIP length on disk). */
  readonly byteLength: number;
  /** Running / finalized SHA-256 of all appended bytes (call after close). */
  digestHex(): string;
  close(): Promise<void>;
}

function uint8ArrayToBase64(bytes: Uint8Array): string {
  const CHUNK = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const slice = bytes.subarray(i, i + CHUNK);
    binary += String.fromCharCode(...slice);
  }
  if (typeof btoa === 'function') {
    return btoa(binary);
  }
  const alphabet =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i]!;
    const b = i + 1 < bytes.length ? bytes[i + 1]! : 0;
    const c = i + 2 < bytes.length ? bytes[i + 2]! : 0;
    const triple = (a << 16) | (b << 8) | c;
    out += alphabet[(triple >> 18) & 63];
    out += alphabet[(triple >> 12) & 63];
    out += i + 1 < bytes.length ? alphabet[(triple >> 6) & 63] : '=';
    out += i + 2 < bytes.length ? alphabet[triple & 63] : '=';
  }
  return out;
}

function fileUriToPath(uri: string): string {
  if (uri.startsWith('file://')) {
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
}

function assertNotAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) {
    throw new ZipWriteError('ZIP_CANCELLED', 'abort during append');
  }
}

/**
 * Create an empty target file and return an append sink that never retains prior ZIP bytes.
 */
export async function createBinaryAppendSink(targetUri: string): Promise<BinaryAppendSink> {
  const hasher = new IncrementalSha256();
  let byteLength = 0;
  let closed = false;
  let finalizedDigest: string | null = null;

  if (isNodeRuntime()) {
    const fs = requireNodeFs();
    const dirname = (p: string): string => {
      const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
      return i <= 0 ? '.' : p.slice(0, i);
    };
    const basename = (p: string): string => {
      const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
      return i < 0 ? p : p.slice(i + 1);
    };
    const join = (...parts: string[]): string =>
      parts
        .filter(Boolean)
        .join('/')
        .replace(/\/+/g, '/');
    let filePath = fileUriToPath(targetUri);
    try {
      fs.mkdirSync(dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, new Uint8Array(0));
    } catch {
      filePath = join(nodeTmpDir(), 'dinamic-zip-sink', basename(filePath) || `zip-${Date.now()}.bin`);
      fs.mkdirSync(dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, new Uint8Array(0));
    }
    return {
      uri: targetUri,
      physicalPath: filePath,
      get byteLength() {
        return byteLength;
      },
      async append(bytes: Uint8Array, signal?: AbortSignal) {
        if (closed) throw new Error('sink closed');
        const MAX_CHUNK = 256 * 1024;
        for (let i = 0; i < bytes.length; i += MAX_CHUNK) {
          assertNotAborted(signal);
          const slice = bytes.subarray(i, Math.min(i + MAX_CHUNK, bytes.length));
          fs.appendFileSync(filePath, slice);
          hasher.update(slice);
          byteLength += slice.length;
        }
      },
      async appendFromFile(sourceAbsolutePath: string, signal?: AbortSignal) {
        if (closed) throw new Error('sink closed');
        assertNotAborted(signal);
        const src = fileUriToPath(sourceAbsolutePath);
        const fd = fs.openSync(src, 'r');
        try {
          const size = fs.fstatSync(fd).size;
          const CHUNK = 256 * 1024;
          const buf = new Uint8Array(CHUNK);
          let offset = 0;
          while (offset < size) {
            assertNotAborted(signal);
            const n = fs.readSync(fd, buf, 0, Math.min(CHUNK, size - offset), offset);
            const slice = buf.subarray(0, n);
            fs.appendFileSync(filePath, slice);
            hasher.update(slice);
            byteLength += n;
            offset += n;
          }
          return size;
        } finally {
          fs.closeSync(fd);
        }
      },
      digestHex() {
        if (finalizedDigest == null) {
          throw new Error('digestHex requires close()');
        }
        return finalizedDigest;
      },
      async close() {
        if (closed) return;
        closed = true;
        finalizedDigest = hasher.digestHex();
      },
    };
  }

  const native: CaptureForegroundAppendNative | null = resolveNativeBinaryAppend();
  if (native) {
    const abs = fileUriToPath(targetUri);
    const dir = targetUri.replace(/\/[^/]+$/, '/');
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
    if (typeof native.truncateFile === 'function') {
      await native.truncateFile(abs);
    } else {
      await FileSystem.writeAsStringAsync(targetUri, '', {
        encoding: FileSystem.EncodingType.UTF8,
      });
    }
    const ra = resolveNativeRandomAccess();
    return {
      uri: targetUri,
      physicalPath: abs,
      get byteLength() {
        return byteLength;
      },
      async append(bytes: Uint8Array, signal?: AbortSignal) {
        if (closed) throw new Error('sink closed');
        // Framing only (small). Photos should use appendFromFile.
        const MAX_CHUNK = 256 * 1024;
        for (let i = 0; i < bytes.length; i += MAX_CHUNK) {
          assertNotAborted(signal);
          const slice = bytes.subarray(i, Math.min(i + MAX_CHUNK, bytes.length));
          await native.appendBase64File(abs, uint8ArrayToBase64(slice));
          byteLength += slice.length;
        }
      },
      async appendFromFile(sourceAbsolutePath: string, signal?: AbortSignal) {
        if (closed) throw new Error('sink closed');
        assertNotAborted(signal);
        if (typeof native.appendFile !== 'function') {
          throw new ZipWriteError(
            'ZIP_WRITE_FAILED',
            `appendFile missing (${missingNativeZipIoDetail()}) — rebuild Android native`,
          );
        }
        const src = fileUriToPath(sourceAbsolutePath);
        const copied = Math.trunc(await native.appendFile(abs, src));
        byteLength += copied;
        return copied;
      },
      digestHex() {
        if (finalizedDigest == null) {
          throw new Error('digestHex requires close()');
        }
        return finalizedDigest;
      },
      async close() {
        if (closed) return;
        closed = true;
        // Disk-authoritative digest (same algorithm as validateOnDiskStoreZip on device).
        if (!ra) {
          throw new ZipWriteError(
            'ZIP_WRITE_FAILED',
            `hashFileSha256 missing (${missingNativeZipIoDetail()})`,
          );
        }
        finalizedDigest = (await ra.hashFileSha256(abs)).toLowerCase();
      },
    };
  }

  throw new ZipWriteError(
    'ZIP_WRITE_FAILED',
    `no binary append sink (${missingNativeZipIoDetail()}). Expo FileSystem cannot stream ZIP without holding the full archive.`,
  );
}
