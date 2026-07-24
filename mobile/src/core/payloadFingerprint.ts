/**
 * FNV-1a 32-bit hash for payload fingerprinting (no crypto dependency).
 * Not for security — only draft idempotency / compare keys.
 */
export function hashPayloadFingerprint(value: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return `fnv1a32:${(h >>> 0).toString(16).padStart(8, '0')}`;
}
