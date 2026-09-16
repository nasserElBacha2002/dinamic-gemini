/**
 * CRC-32 (ISO 3309 / ZIP) — table-driven, independent of SHA-256.
 */

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

/** Update running CRC-32 (initial value 0). */
export function crc32Update(crc: number, bytes: Uint8Array): number {
  let c = (crc ^ 0xffffffff) >>> 0;
  for (let i = 0; i < bytes.length; i += 1) {
    c = CRC_TABLE[(c ^ bytes[i]!) & 0xff]! ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

export function crc32Bytes(bytes: Uint8Array): number {
  return crc32Update(0, bytes);
}

/** Known vector: CRC32("123456789") = 0xcbf43926 */
export const CRC32_VECTOR_123456789 = 0xcbf43926;
