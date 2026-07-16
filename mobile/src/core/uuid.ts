/**
 * UUID v4 generation for client-side identifiers (`upload_batch_id`, `client_file_id`).
 *
 * These ids are idempotency keys, not security tokens, so a `Math.random` fallback is
 * acceptable when no native CSPRNG is exposed on `globalThis.crypto`. Prefers
 * `crypto.randomUUID()` / `crypto.getRandomValues()` when available (Hermes/RN with
 * `expo-crypto` polyfill installed, or Node in tests).
 */

type CryptoLike = {
  randomUUID?: () => string;
  getRandomValues?: (array: Uint8Array) => Uint8Array;
};

function formatUuidBytes(bytes: Uint8Array | number[]): string {
  const b = Array.from(bytes);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const hex = b.map((byte) => byte.toString(16).padStart(2, '0'));
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}

/** Pure fallback: RFC 4122 v4 via a supplied RNG (defaults to `Math.random`). Unit-testable. */
export function createUuidV4(random: () => number = Math.random): string {
  const bytes: number[] = [];
  for (let i = 0; i < 16; i += 1) {
    bytes.push(Math.floor(random() * 256));
  }
  return formatUuidBytes(bytes);
}

/** Best available UUID v4: native `crypto.randomUUID`/`getRandomValues`, else pure fallback. */
export function createUuid(): string {
  const globalCrypto = (globalThis as { crypto?: CryptoLike }).crypto;
  if (typeof globalCrypto?.randomUUID === 'function') {
    return globalCrypto.randomUUID();
  }
  if (typeof globalCrypto?.getRandomValues === 'function') {
    const bytes = globalCrypto.getRandomValues(new Uint8Array(16));
    return formatUuidBytes(bytes);
  }
  return createUuidV4();
}
