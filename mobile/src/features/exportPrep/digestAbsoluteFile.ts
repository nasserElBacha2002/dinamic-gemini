/**
 * Digest an on-disk file (size + SHA-256 + CRC-32) without loading the whole file into JS RAM.
 * Android: CaptureForegroundService.digestFile. Node: streaming fs + IncrementalSha256/crc32.
 */

import { crc32StreamFeed, crc32StreamFinal, crc32StreamInit } from './crc32';
import { IncrementalSha256 } from './incrementalSha256';
import { isNodeRuntime } from './nodeRuntime';
import { requireNodeFs } from './requireNodeFs';
import {
  getNativeBinaryCapabilities,
  resolveNativeBinaryAppend,
} from './captureForegroundNative';

export type FileDigest = {
  readonly size: number;
  readonly sha256: string;
  readonly crc32: number;
};

export class DigestCapabilityError extends Error {
  readonly code = 'DIGEST_UNAVAILABLE' as const;
  constructor(message: string) {
    super(message);
    this.name = 'DigestCapabilityError';
  }
}

export class DigestIoError extends Error {
  readonly code = 'DIGEST_IO_FAILED' as const;
  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'DigestIoError';
    if (cause !== undefined) {
      (this as { cause?: unknown }).cause = cause;
    }
  }
}

function fileUriToPath(uri: string): string {
  if (uri.startsWith('file://')) {
    // decodeURIComponent preserves '+' (unlike form-urlencoded URLDecoder).
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
}

/**
 * Assert native digestFile is available on Android before staging hash.
 * Node test/tooling paths are always capable (streaming fs).
 */
export function assertNativeDigestCapability(): void {
  if (isNodeRuntime()) {
    return;
  }
  const caps = getNativeBinaryCapabilities();
  if (!caps.digestFile) {
    throw new DigestCapabilityError(
      'digestFile unavailable — rebuild Android native (appendFile/digestFile). Deploy APK with digestFile before this JS bundle.',
    );
  }
}

export async function digestAbsoluteFile(uriOrPath: string): Promise<FileDigest> {
  const abs = fileUriToPath(uriOrPath);

  if (isNodeRuntime()) {
    const fs = requireNodeFs();
    let fd: number;
    try {
      fd = fs.openSync(abs, 'r');
    } catch (error) {
      throw new DigestIoError(
        error instanceof Error ? error.message : 'failed to open file for digest',
        error,
      );
    }
    try {
      const size = fs.fstatSync(fd).size;
      const hasher = new IncrementalSha256();
      let crcState = crc32StreamInit();
      const CHUNK = 256 * 1024;
      const buf = new Uint8Array(CHUNK);
      let offset = 0;
      while (offset < size) {
        const n = fs.readSync(fd, buf, 0, Math.min(CHUNK, size - offset), offset);
        const slice = buf.subarray(0, n);
        hasher.update(slice);
        crcState = crc32StreamFeed(crcState, slice);
        offset += n;
      }
      return { size, sha256: hasher.digestHex(), crc32: crc32StreamFinal(crcState) };
    } catch (error) {
      if (error instanceof DigestIoError) throw error;
      throw new DigestIoError(
        error instanceof Error ? error.message : 'digest read failed',
        error,
      );
    } finally {
      try {
        fs.closeSync(fd!);
      } catch {
        /* ignore */
      }
    }
  }

  assertNativeDigestCapability();
  const native = resolveNativeBinaryAppend();
  if (!native?.digestFile) {
    throw new DigestCapabilityError(
      'digestFile unavailable — rebuild Android native (appendFile/digestFile)',
    );
  }

  try {
    return await native.digestFile(abs);
  } catch (error) {
    if (error instanceof DigestCapabilityError) throw error;
    const message = error instanceof Error ? error.message : 'native digestFile failed';
    if (/unavailable|not a function|undefined is not/i.test(message)) {
      throw new DigestCapabilityError(message);
    }
    throw new DigestIoError(message, error);
  }
}
