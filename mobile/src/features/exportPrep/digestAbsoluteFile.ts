/**
 * Digest an on-disk file (size + SHA-256 + CRC-32) without loading the whole file into JS RAM.
 * Android: CaptureForegroundService.digestFile. Node: streaming fs + IncrementalSha256/crc32.
 */

import { crc32StreamFeed, crc32StreamFinal, crc32StreamInit } from './crc32';
import { IncrementalSha256 } from './incrementalSha256';
import { isNodeRuntime } from './nodeRuntime';
import { requireNodeFs } from './requireNodeFs';
import { resolveNativeBinaryAppend } from './captureForegroundNative';

export type FileDigest = {
  readonly size: number;
  readonly sha256: string;
  readonly crc32: number;
};

function fileUriToPath(uri: string): string {
  if (uri.startsWith('file://')) {
    return decodeURIComponent(uri.slice('file://'.length));
  }
  return uri;
}

export async function digestAbsoluteFile(uriOrPath: string): Promise<FileDigest> {
  const abs = fileUriToPath(uriOrPath);

  if (isNodeRuntime()) {
    const fs = requireNodeFs();
    const fd = fs.openSync(abs, 'r');
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
    } finally {
      fs.closeSync(fd);
    }
  }

  const native = resolveNativeBinaryAppend();
  if (native?.digestFile) {
    return native.digestFile(abs);
  }

  throw new Error(
    'digestFile unavailable — rebuild Android native (appendFile/digestFile)',
  );
}
