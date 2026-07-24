/**
 * Decode standard base64 into bytes (RN / Node compatible).
 */
export function base64ToBytes(b64: string): Uint8Array {
  const normalized = b64.replace(/\s/g, '');
  if (typeof Buffer !== 'undefined') {
    return Uint8Array.from(Buffer.from(normalized, 'base64'));
  }
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const lookup = new Uint8Array(256);
  for (let i = 0; i < chars.length; i += 1) {
    lookup[chars.charCodeAt(i)] = i;
  }
  let padding = 0;
  if (normalized.endsWith('==')) padding = 2;
  else if (normalized.endsWith('=')) padding = 1;
  const len = normalized.length;
  const outLen = ((len * 3) / 4) | 0 - padding;
  const out = new Uint8Array(outLen);
  let p = 0;
  for (let i = 0; i < len; i += 4) {
    const a = lookup[normalized.charCodeAt(i)] ?? 0;
    const b = lookup[normalized.charCodeAt(i + 1)] ?? 0;
    const c = lookup[normalized.charCodeAt(i + 2)] ?? 0;
    const d = lookup[normalized.charCodeAt(i + 3)] ?? 0;
    out[p++] = (a << 2) | (b >> 4);
    if (p < outLen) out[p++] = ((b & 15) << 4) | (c >> 2);
    if (p < outLen) out[p++] = ((c & 3) << 6) | d;
  }
  return out;
}
