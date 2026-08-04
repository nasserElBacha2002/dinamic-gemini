/** Small base64 ↔ bytes helpers for ZIP packaging (Hermes / RN). */

export function base64ToUint8Array(b64: string): Uint8Array {
  const atobFn = globalThis.atob;
  if (typeof atobFn !== 'function') {
    throw new Error('atob no disponible para decodificar la fotografía.');
  }
  const binary = atobFn(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

export function uint8ArrayToBase64(bytes: Uint8Array): string {
  const btoaFn = globalThis.btoa;
  if (typeof btoaFn !== 'function') {
    throw new Error('btoa no disponible para codificar el ZIP.');
  }
  const chunk = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += chunk) {
    const slice = bytes.subarray(i, Math.min(i + chunk, bytes.length));
    let part = '';
    for (let j = 0; j < slice.length; j += 1) {
      part += String.fromCharCode(slice[j]!);
    }
    binary += part;
  }
  return btoaFn(binary);
}
