/**
 * Bounded-memory ZIP builder for local aisle export.
 *
 * Reads one entry at a time (caller supplies getBytes). Uses fflate STORE (ZipPassThrough).
 *
 * TECHNICAL LIMITATION (Expo SDK 51 / expo-file-system ~17):
 * There is no supported API to append raw binary chunks to a file without Base64.
 * Therefore the final ZIP bytes are still held in memory once, then written via Base64.
 * Peak memory ≈ max(single entry) + final ZIP size (+ Base64 during write), NOT
 * sum(all photo buffers) + ZIP + Base64 simultaneously.
 *
 * True disk-streaming ZIP write requires a native module or Expo FS upgrade — documented
 * in incremental-zip-implementation-report.md; not faked here.
 */
import { Zip, ZipPassThrough } from 'fflate';
import * as FileSystem from 'expo-file-system';

import { sha256BytesHex } from '../../core/payloadFingerprint';

export interface StreamingZipEntry {
  readonly path: string;
  readonly getBytes: () => Promise<Uint8Array> | Uint8Array;
}

function uint8ArrayToBase64(bytes: Uint8Array): string {
  // Chunked to avoid call-stack / argument limits on large arrays.
  const CHUNK = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const slice = bytes.subarray(i, i + CHUNK);
    binary += String.fromCharCode(...slice);
  }
  // btoa available in RN hermes / jest with polyfill; fallback Buffer in node tests.
  if (typeof btoa === 'function') {
    return btoa(binary);
  }
  return Buffer.from(bytes).toString('base64');
}

export async function buildStoreZipBytes(entries: readonly StreamingZipEntry[]): Promise<Uint8Array> {
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
          // bytes eligible for GC after push; do not retain references
        }
        zip.end();
      } catch (error) {
        reject(error);
      }
    })();
  });
}

/**
 * Build STORE ZIP and publish atomically via tmp + move.
 * Reports progress as entries completed (0..entries.length).
 */
export async function writeStoreZipAtomic(input: {
  readonly entries: readonly StreamingZipEntry[];
  readonly targetUri: string;
  readonly onProgress?: (done: number, total: number) => void;
}): Promise<{ readonly byteLength: number; readonly sha256: string }> {
  const total = input.entries.length;
  let done = 0;
  const wrapped: StreamingZipEntry[] = input.entries.map((e) => ({
    path: e.path,
    getBytes: async () => {
      const bytes = await e.getBytes();
      done += 1;
      input.onProgress?.(done, total);
      return bytes;
    },
  }));

  const zipped = await buildStoreZipBytes(wrapped);
  const dir = input.targetUri.replace(/\/[^/]+$/, '/');
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
  const tmpUri = `${input.targetUri}.tmp.${Date.now()}`;
  const b64 = uint8ArrayToBase64(zipped);
  try {
    await FileSystem.writeAsStringAsync(tmpUri, b64, {
      encoding: FileSystem.EncodingType.Base64,
    });
    await FileSystem.deleteAsync(input.targetUri, { idempotent: true }).catch(() => undefined);
    await FileSystem.moveAsync({ from: tmpUri, to: input.targetUri });
  } catch (error) {
    await FileSystem.deleteAsync(tmpUri, { idempotent: true }).catch(() => undefined);
    throw error;
  }
  return { byteLength: zipped.byteLength, sha256: sha256BytesHex(zipped) };
}
