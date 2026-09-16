/**
 * Binary append sink for bounded ZIP writes.
 *
 * Expo FileSystem (SDK 51 / ~17) cannot append binary without loading the whole file.
 * On Android we use CaptureForegroundService.appendBase64File (FileOutputStream append).
 * In Node/Jest we use fs.appendFile. No in-memory accumulation of prior ZIP bytes.
 */

import * as FileSystem from 'expo-file-system';

import { IncrementalSha256 } from './incrementalSha256';

export interface BinaryAppendSink {
  readonly uri: string;
  append(bytes: Uint8Array): Promise<void>;
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
  return Buffer.from(bytes).toString('base64');
}

function fileUriToPath(uri: string): string {
  if (uri.startsWith('file://')) {
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
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

function isNodeRuntime(): boolean {
  return typeof process !== 'undefined' && Boolean(process.versions?.node);
}

/**
 * Create an empty target file and return an append sink that never retains prior ZIP bytes.
 */
export async function createBinaryAppendSink(targetUri: string): Promise<BinaryAppendSink> {
  const hasher = new IncrementalSha256();
  let byteLength = 0;
  let closed = false;

  if (isNodeRuntime()) {
    // Literal require('fs'): Jest → real Node; Metro → metro-shims/node-builtin.js
    // (branch never runs on device). Avoid require('path'|'os') so Metro need not stub them.
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
    const tmpdir = (): string =>
      process.env.TMPDIR || process.env.TMP || process.env.TEMP || '/tmp';
    let filePath = fileUriToPath(targetUri);
    try {
      fs.mkdirSync(dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, new Uint8Array(0));
    } catch {
      // Jest stubs often use file:///docs which is not writable — fall back to tmp.
      filePath = join(tmpdir(), 'dinamic-zip-sink', basename(filePath) || `zip-${Date.now()}.bin`);
      fs.mkdirSync(dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, new Uint8Array(0));
    }
    return {
      uri: targetUri,
      get byteLength() {
        return byteLength;
      },
      async append(bytes: Uint8Array) {
        if (closed) throw new Error('sink closed');
        fs.appendFileSync(filePath, bytes);
        hasher.update(bytes);
        byteLength += bytes.length;
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
      get byteLength() {
        return byteLength;
      },
      async append(bytes: Uint8Array) {
        if (closed) throw new Error('sink closed');
        // Chunk Base64 appends so a single encode never holds >> one entry.
        const MAX_CHUNK = 256 * 1024;
        for (let i = 0; i < bytes.length; i += MAX_CHUNK) {
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

  throw new Error(
    'ZIP_WRITE_FAILED: no binary append sink (native appendBase64File / Node fs). Expo FileSystem cannot stream ZIP without holding the full archive.',
  );
}
