/**
 * Mobile Phase 3 — encoded label payload grammar aligned with server
 * `parse_inventory_code_payload` + `EncodedLabelPayloadParser`.
 * Authority: contracts/code-scan/v1 + backend Phase 3 docs.
 */

export const LABEL_PAYLOAD_PARSER_VERSION = '1.0.0';
export const CODE_MAX_LENGTH = 48;
export const QUANTITY_MAX_DEFAULT = 99_999_999;
export const QUANTITY_PATTERN = /^[1-9]\d{0,7}$/;

const DI1_PATTERN = /^DI1\|C=([^|]+)\|Q=([1-9]\d{0,7})$/i;
const PIPE_PATTERN = /^([^|\n]{1,48})\|([1-9]\d{0,7})$/;
const LABELED_CODE_PATTERN = /^\s*C[oó]digo interno:\s*(.+)\s*$/im;

export type LabelPayloadFormat = 'PIPE' | 'DI1' | 'LABELED' | 'PLAIN' | 'UNKNOWN';
export type QuantityStatus = 'PRESENT' | 'MISSING' | 'INVALID';

export type PayloadParseErrorCode =
  | 'EMPTY_OR_UNPARSEABLE_PAYLOAD'
  | 'NO_INTERNAL_CODE'
  | 'CODE_LENGTH_OUT_OF_RANGE'
  | 'CODE_CONTROL_CHARACTERS'
  | 'QUANTITY_MISSING'
  | 'QUANTITY_NOT_POSITIVE'
  | 'QUANTITY_ABOVE_MAX'
  | 'QUANTITY_NOT_INTEGER';

export type PayloadParseResult =
  | {
      status: 'VALID';
      format: LabelPayloadFormat;
      internalCode: string;
      quantity: number | null;
      quantityStatus: QuantityStatus;
      formatVersion: string;
      warnings: readonly string[];
      errorCode?: undefined;
    }
  | {
      status: 'INVALID';
      format: LabelPayloadFormat;
      internalCode: null;
      quantity: number | null;
      quantityStatus: QuantityStatus;
      formatVersion: string;
      errorCode: PayloadParseErrorCode;
      warnings: readonly string[];
    };

function hasControlChars(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const c = value.charCodeAt(i);
    if (c < 0x20 || c === 0x7f) {
      return true;
    }
  }
  return false;
}

function detectFormat(raw: string): LabelPayloadFormat {
  const text = raw.trim();
  if (DI1_PATTERN.test(text)) return 'DI1';
  if (PIPE_PATTERN.test(text)) return 'PIPE';
  if (LABELED_CODE_PATTERN.test(text)) return 'LABELED';
  return 'PLAIN';
}

/** Mirror of Python parse_inventory_code_payload (raises on empty). */
export function parseInventoryCodePayloadGrammar(raw: string): {
  internalCode: string;
  quantity: number | null;
} {
  const text = (raw ?? '').trim();
  if (!text) {
    throw new Error('empty payload');
  }

  const di1 = text.match(DI1_PATTERN);
  if (di1) {
    let code: string;
    try {
      code = decodeURIComponent(di1[1] ?? '').trim();
    } catch {
      throw new Error('invalid DI1 escape');
    }
    return { internalCode: code, quantity: Number.parseInt(di1[2] ?? '', 10) };
  }

  const pipe = text.match(PIPE_PATTERN);
  if (pipe) {
    return {
      internalCode: (pipe[1] ?? '').trim(),
      quantity: Number.parseInt(pipe[2] ?? '', 10),
    };
  }

  const labeled = text.match(LABELED_CODE_PATTERN);
  if (labeled) {
    const code = (labeled[1] ?? '').split('\n')[0]?.trim() ?? '';
    if (code) {
      return { internalCode: code, quantity: null };
    }
  }

  const first = text.split('\n', 1)[0]?.trim() ?? '';
  if (!first) {
    throw new Error('empty payload');
  }
  return { internalCode: first.slice(0, CODE_MAX_LENGTH), quantity: null };
}

/**
 * Full parse + validation (EncodedLabelPayloadParser semantics).
 */
export function parseEncodedLabelPayload(
  raw: string,
  options?: { readonly quantityMax?: number; readonly codeMaxLength?: number },
): PayloadParseResult {
  const quantityMax = options?.quantityMax ?? QUANTITY_MAX_DEFAULT;
  const codeMaxLength = options?.codeMaxLength ?? CODE_MAX_LENGTH;
  const rawValue = raw ?? '';
  const warnings: string[] = [];

  let grammar: { internalCode: string; quantity: number | null };
  try {
    grammar = parseInventoryCodePayloadGrammar(rawValue);
  } catch {
    return {
      status: 'INVALID',
      format: 'UNKNOWN',
      internalCode: null,
      quantity: null,
      quantityStatus: 'MISSING',
      formatVersion: 'v1',
      errorCode: 'EMPTY_OR_UNPARSEABLE_PAYLOAD',
      warnings: ['EMPTY_OR_UNPARSEABLE_PAYLOAD'],
    };
  }

  const format = detectFormat(rawValue);
  let code: string | null = grammar.internalCode || null;
  const rawQuantity = grammar.quantity;

  if (!code) {
    warnings.push('NO_INTERNAL_CODE');
    code = null;
  } else if (code.length < 1 || code.length > codeMaxLength) {
    warnings.push('CODE_LENGTH_OUT_OF_RANGE');
    code = null;
  } else if (hasControlChars(code)) {
    warnings.push('CODE_CONTROL_CHARACTERS');
    code = null;
  }

  let quantity: number | null = null;
  let quantityStatus: QuantityStatus = 'MISSING';
  if (rawQuantity == null) {
    warnings.push('QUANTITY_MISSING');
    quantityStatus = 'MISSING';
  } else if (!Number.isInteger(rawQuantity)) {
    warnings.push('QUANTITY_NOT_INTEGER');
    quantityStatus = 'INVALID';
  } else if (rawQuantity <= 0) {
    warnings.push('QUANTITY_NOT_POSITIVE');
    quantityStatus = 'INVALID';
  } else if (rawQuantity > quantityMax) {
    warnings.push('QUANTITY_ABOVE_MAX');
    quantityStatus = 'INVALID';
  } else {
    quantity = rawQuantity;
    quantityStatus = 'PRESENT';
  }

  if (!code) {
    const errorCode = (warnings.find((w) =>
      [
        'EMPTY_OR_UNPARSEABLE_PAYLOAD',
        'NO_INTERNAL_CODE',
        'CODE_LENGTH_OUT_OF_RANGE',
        'CODE_CONTROL_CHARACTERS',
      ].includes(w),
    ) ?? 'NO_INTERNAL_CODE') as PayloadParseErrorCode;
    return {
      status: 'INVALID',
      format,
      internalCode: null,
      quantity,
      quantityStatus,
      formatVersion: format === 'DI1' ? 'DI1' : 'v1',
      errorCode,
      warnings,
    };
  }

  return {
    status: 'VALID',
    format,
    internalCode: code,
    quantity,
    quantityStatus,
    formatVersion: format === 'DI1' ? 'DI1' : 'v1',
    warnings,
  };
}
