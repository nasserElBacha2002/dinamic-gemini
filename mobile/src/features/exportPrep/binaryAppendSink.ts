/**
 * Binary append sink for bounded ZIP writes.
 *
 * Expo FileSystem (SDK 51 / ~17) cannot append binary without loading the whole file.
 * On Android we use CaptureForegroundService.appendBase64File (FileOutputStream append).
 * In Node/Jest we use fs.appendFile. No in-memory accumulation of prior ZIP bytes.
 */

import * as FileSystem from 'expo-file-system';

import { IncrementalSha256 } from './incrementalSha256';
import { ZipWriteError } from './boundedZipWriter';
import { isNodeRuntime, nodeTmpDir } from './nodeRuntime';

export interface BinaryAppendSink {
  readonly uri: string;
  /** Absolute filesystem path used for I/O (may differ from uri under Jest stubs). */
  readonly physicalPath: string;
  append(bytes: Uint8Array, signal?: AbortSignal): Promise<void>;
  /** Bytes written so far (uncompressed ZIP length on disk). */
  readonly byteLength: number;
  /** Running SHA-256 of all appended bytes. */
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
  // Jest/Node without btoa: encode manually (probe/test only).
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

type NativeAppend = {
  appendBase64File: (absolutePath: string, base64: string) => Promise<void>;
  truncateFile?: (absolutePath: string) => Promise<void>;
};

function resolveNativeAppend(): NativeAppend | null {
  let os: string | undefined;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    os = (require('react-native') as { Platform?: { OS?: string } }).Platform?.OS;
  } catch {
    return null;
  }
  if (os !== 'android') {
    return null;
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { requireOptionalNativeModule } = require('expo-modules-core') as {
      requireOptionalNativeModule: (name: string) => NativeAppend | null;
    };
    const mod = requireOptionalNativeModule('CaptureForegroundService');
    if (mod && typeof mod.appendBase64File === 'function') {
      return mod;
    }
  } catch {
    /* unavailable in this runtime */
  }
  return null;
}

/**
 * Create an empty target file and return an append sink that never retains prior ZIP bytes.
 */
export async function createBinaryAppendSink(targetUri: string): Promise<BinaryAppendSink> {
  const hasher = new IncrementalSha256();
  let byteLength = 0;
  let closed = false;

  if (isNodeRuntime()) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require('fs') as typeof import('fs');
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
      digestHex() {
        return hasher.digestHex();
      },
      async close() {
        closed = true;
      },
    };
  }

  const native = resolveNativeAppend();
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
    return {
      uri: targetUri,
      physicalPath: abs,
      get byteLength() {
        return byteLength;
      },
      async append(bytes: Uint8Array, signal?: AbortSignal) {
        if (closed) throw new Error('sink closed');
        const MAX_CHUNK = 256 * 1024;
        for (let i = 0; i < bytes.length; i += MAX_CHUNK) {
          assertNotAborted(signal);
          const slice = bytes.subarray(i, Math.min(i + MAX_CHUNK, bytes.length));
          await native.appendBase64File(abs, uint8ArrayToBase64(slice));
          hasher.update(slice);
          byteLength += slice.length;
        }
      },
      digestHex() {
        return hasher.digestHex();
      },
      async close() {
        closed = true;
      },
    };
  }

  throw new ZipWriteError(
    'ZIP_WRITE_FAILED',
    'no binary append sink (native appendBase64File / Node fs). Expo FileSystem cannot stream ZIP without holding the full archive.',
  );
}
