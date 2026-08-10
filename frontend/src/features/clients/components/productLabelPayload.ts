/**
 * Dinamic physical product label payload (D1) — shared with backend + mobile.
 * Format: D1|<label_id>|<internal_code>|<quantity>|<checksum>
 * Checksum is read-integrity only (not authentication / not identity).
 */

export const PRODUCT_LABEL_FORMAT_VERSION = 'D1' as const;
export const PRODUCT_LABEL_ID_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
export const PRODUCT_LABEL_ID_LENGTH = 10;
export const PRODUCT_LABEL_CHECKSUM_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
/** D1 payloads can be longer than legacy PIPE; keep CODE128 printable. */
export const PRODUCT_LABEL_PAYLOAD_MAX_LENGTH = 96;

const D1_PATTERN =
  /^D1\|([0-9A-HJKMNP-TV-Z]{10})\|([^|\n]{1,48})\|([1-9]\d{0,7})\|([0-9A-Z])$/i;

export type ProductLabelValidationStatus =
  | 'VALID'
  | 'NOT_OUR_FORMAT'
  | 'CHECKSUM_FAILED'
  | 'MALFORMED'
  | 'UNKNOWN_VERSION'
  | 'QUANTITY_INVALID'
  | 'LABEL_ID_INVALID';

export interface ParsedProductLabelPayload {
  readonly status: ProductLabelValidationStatus;
  readonly formatVersion: string | null;
  readonly labelId: string | null;
  readonly internalCode: string | null;
  readonly quantity: number | null;
  readonly checksumReceived: string | null;
  readonly checksumExpected: string | null;
  readonly rawValue: string;
  readonly normalizedPayload: string | null;
  readonly detail?: string;
}

export function normalizeProductLabelRaw(raw: string): string {
  return (raw ?? '').trim();
}

function checksumChar(body: string): string {
  let total = 0;
  const upper = body.toUpperCase();
  for (let i = 0; i < upper.length; i += 1) {
    const ch = upper[i]!;
    const idx = PRODUCT_LABEL_CHECKSUM_ALPHABET.indexOf(ch);
    const val = idx >= 0 ? idx : ch.charCodeAt(0) % 36;
    total = (total + val * (i + 1)) % 36;
  }
  return PRODUCT_LABEL_CHECKSUM_ALPHABET[total]!;
}

export function computeProductLabelChecksum(input: {
  labelId: string;
  internalCode: string;
  quantity: number;
  formatVersion?: string;
}): string {
  const version = input.formatVersion ?? PRODUCT_LABEL_FORMAT_VERSION;
  const body = `${version}|${input.labelId}|${input.internalCode}|${input.quantity}`;
  return checksumChar(body);
}

export function buildProductLabelPayload(input: {
  labelId: string;
  internalCode: string;
  quantity: number;
  formatVersion?: string;
}): string {
  const version = input.formatVersion ?? PRODUCT_LABEL_FORMAT_VERSION;
  const labelId = input.labelId.trim().toUpperCase();
  const code = input.internalCode.trim();
  const idRe = new RegExp(`^[${PRODUCT_LABEL_ID_ALPHABET}]{${PRODUCT_LABEL_ID_LENGTH}}$`);
  if (!idRe.test(labelId)) {
    throw new Error('invalid label_id');
  }
  if (!code || code.includes('|') || code.length > 48) {
    throw new Error('invalid internal_code');
  }
  if (!Number.isInteger(input.quantity) || input.quantity < 1 || input.quantity > 99_999_999) {
    throw new Error('invalid quantity');
  }
  const checksum = computeProductLabelChecksum({
    labelId,
    internalCode: code,
    quantity: input.quantity,
    formatVersion: version,
  });
  const payload = `${version}|${labelId}|${code}|${input.quantity}|${checksum}`;
  if (payload.length > PRODUCT_LABEL_PAYLOAD_MAX_LENGTH) {
    throw new Error('payload too long');
  }
  return payload;
}

export function parseProductLabelPayload(raw: string): ParsedProductLabelPayload {
  const text = normalizeProductLabelRaw(raw);
  if (!text) {
    return {
      status: 'MALFORMED',
      formatVersion: null,
      labelId: null,
      internalCode: null,
      quantity: null,
      checksumReceived: null,
      checksumExpected: null,
      rawValue: raw ?? '',
      normalizedPayload: null,
      detail: 'empty',
    };
  }

  if (/^D\d+\|/i.test(text) && !text.toUpperCase().startsWith('D1|')) {
    return {
      status: 'UNKNOWN_VERSION',
      formatVersion: text.split('|', 1)[0]?.toUpperCase() ?? null,
      labelId: null,
      internalCode: null,
      quantity: null,
      checksumReceived: null,
      checksumExpected: null,
      rawValue: text,
      normalizedPayload: null,
      detail: 'unsupported format version',
    };
  }

  const match = D1_PATTERN.exec(text);
  if (!match) {
    return {
      status: 'NOT_OUR_FORMAT',
      formatVersion: null,
      labelId: null,
      internalCode: null,
      quantity: null,
      checksumReceived: null,
      checksumExpected: null,
      rawValue: text,
      normalizedPayload: null,
      detail: 'not D1 product label',
    };
  }

  const labelId = match[1]!.toUpperCase();
  const internalCode = match[2]!.trim();
  const quantity = Number.parseInt(match[3]!, 10);
  const checksumReceived = match[4]!.toUpperCase();
  const checksumExpected = computeProductLabelChecksum({
    labelId,
    internalCode,
    quantity,
  });
  const normalizedPayload = buildProductLabelPayload({
    labelId,
    internalCode,
    quantity,
  });
  if (checksumReceived !== checksumExpected) {
    return {
      status: 'CHECKSUM_FAILED',
      formatVersion: PRODUCT_LABEL_FORMAT_VERSION,
      labelId,
      internalCode,
      quantity,
      checksumReceived,
      checksumExpected,
      rawValue: text,
      normalizedPayload,
      detail: 'checksum mismatch',
    };
  }
  return {
    status: 'VALID',
    formatVersion: PRODUCT_LABEL_FORMAT_VERSION,
    labelId,
    internalCode,
    quantity,
    checksumReceived,
    checksumExpected,
    rawValue: text,
    normalizedPayload,
  };
}
