/**
 * Dinamic physical product label (D1) — mirrors backend domain/product_labels/format.py
 * and contracts/product-labels/v1/checksum-vectors.json.
 */

export const PRODUCT_LABEL_FORMAT_VERSION = 'D1' as const;
export const PRODUCT_LABEL_ID_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
export const PRODUCT_LABEL_ID_LENGTH = 10;
export const PRODUCT_LABEL_CHECKSUM_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';

const D1_PATTERN =
  /^D1\|([0-9A-HJKMNP-TV-Z]{10})\|([^|\n]{1,48})\|([1-9]\d{0,7})\|([0-9A-Z])$/i;

export type ProductLabelValidationStatus =
  | 'VALID'
  | 'NOT_OUR_FORMAT'
  | 'CHECKSUM_FAILED'
  | 'MALFORMED'
  | 'UNKNOWN_VERSION';

export type ParsedProductLabelPayload = {
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
};

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
  return checksumChar(`${version}|${input.labelId}|${input.internalCode}|${input.quantity}`);
}

export function buildProductLabelPayload(input: {
  labelId: string;
  internalCode: string;
  quantity: number;
}): string {
  const labelId = input.labelId.trim().toUpperCase();
  const code = input.internalCode.trim();
  const checksum = computeProductLabelChecksum({
    labelId,
    internalCode: code,
    quantity: input.quantity,
  });
  return `D1|${labelId}|${code}|${input.quantity}|${checksum}`;
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
    };
  }
  const match = D1_PATTERN.exec(text);
  if (!match) {
    // Any D1|… that fails the strict grammar is still a D1 *candidate*.
    // Must not fall through as NOT_OUR_FORMAT (that enables legacy revival).
    if (/^D1\|/i.test(text)) {
      const parts = text.split('|');
      return {
        status: 'MALFORMED',
        formatVersion: 'D1',
        labelId: parts[1] ? parts[1].trim().toUpperCase() || null : null,
        internalCode: parts[2] ? parts[2].trim() || null : null,
        quantity: null,
        checksumReceived: parts[4] ? parts[4].trim().toUpperCase() || null : null,
        checksumExpected: null,
        rawValue: text,
        normalizedPayload: null,
        detail: 'd1_grammar_mismatch',
      };
    }
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
  const normalizedPayload = buildProductLabelPayload({ labelId, internalCode, quantity });
  if (checksumReceived !== checksumExpected) {
    return {
      status: 'CHECKSUM_FAILED',
      formatVersion: 'D1',
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
    formatVersion: 'D1',
    labelId,
    internalCode,
    quantity,
    checksumReceived,
    checksumExpected,
    rawValue: text,
    normalizedPayload,
  };
}
