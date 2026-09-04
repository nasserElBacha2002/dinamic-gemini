import { Zip, ZipPassThrough } from 'fflate';

export interface ZipEntrySource {
  readonly path: string;
  readonly getBytes: () => Promise<Uint8Array> | Uint8Array;
}

/**
 * Builds a ZIP incrementally: one entry at a time in memory (max ≈ largest single entry + zip overhead).
 * Does not retain all asset payloads simultaneously.
 */
export async function buildZipBytes(entries: readonly ZipEntrySource[]): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const chunks: Uint8Array[] = [];
    const zip = new Zip((err, chunk, final) => {
      if (err) {
        reject(err);
        return;
      }
      if (chunk) {
        chunks.push(chunk);
      }
      if (final) {
        const total = chunks.reduce((sum, c) => sum + c.length, 0);
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
