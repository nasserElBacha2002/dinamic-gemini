/** Versioned CODE128 payload for warehouse labels: code + quantity. */

export const LABEL_BARCODE_VERSION = 'DI1' as const;

/** Max trimmed internal code length (print + scan). */
export const LABEL_CODE_MAX_LENGTH = 48;

/**
 * Max encoded payload length for CODE128 inside the printable barcode area.
 * Longer payloads are rejected (no silent clipping).
 */
export const LABEL_BARCODE_PAYLOAD_MAX_LENGTH = 56;

/** Positive integers 1–99999999; no leading zeros, decimals, or thousand separators. */
export const LABEL_QUANTITY_PATTERN = /^[1-9]\d{0,7}$/;

export interface LabelBarcodeData {
  code: string;
  quantity: string;
}

export interface ParsedLabelBarcode {
  version: typeof LABEL_BARCODE_VERSION;
  code: string;
  quantity: string;
}

export class LabelBarcodePayloadError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'LabelBarcodePayloadError';
    this.code = code;
  }
}

export function normalizeLabelCode(value: string): string {
  return value.trim();
}

export function normalizeLabelQuantity(value: string): string {
  return value.trim();
}

export function isValidLabelCode(value: string): boolean {
  const normalized = normalizeLabelCode(value);
  return normalized.length > 0 && normalized.length <= LABEL_CODE_MAX_LENGTH;
}

export function isValidLabelQuantity(value: string): boolean {
  return LABEL_QUANTITY_PATTERN.test(normalizeLabelQuantity(value));
}

/** Module bar width for JsBarcode — narrower for longer payloads so bars fit. */
export function barcodeModuleWidth(payload: string): number {
  if (payload.length <= 20) return 1.5;
  if (payload.length <= 30) return 1.25;
  if (payload.length <= 40) return 1;
  return 0.85;
}

export function buildLabelBarcodePayload({ code, quantity }: LabelBarcodeData): string {
  const normalizedCode = normalizeLabelCode(code);
  const normalizedQuantity = normalizeLabelQuantity(quantity);

  if (!normalizedCode) {
    throw new LabelBarcodePayloadError('EMPTY_CODE', 'El código interno es obligatorio.');
  }
  if (normalizedCode.length > LABEL_CODE_MAX_LENGTH) {
    throw new LabelBarcodePayloadError('CODE_TOO_LONG', 'El código interno es demasiado largo.');
  }
  if (!normalizedQuantity) {
    throw new LabelBarcodePayloadError('EMPTY_QUANTITY', 'La cantidad total es obligatoria.');
  }
  if (!LABEL_QUANTITY_PATTERN.test(normalizedQuantity)) {
    throw new LabelBarcodePayloadError(
      'INVALID_QUANTITY',
      'La cantidad debe ser un entero positivo sin decimales ni separadores.'
    );
  }

  const payload = [
    LABEL_BARCODE_VERSION,
    `C=${encodeURIComponent(normalizedCode)}`,
    `Q=${normalizedQuantity}`,
  ].join('|');

  if (payload.length > LABEL_BARCODE_PAYLOAD_MAX_LENGTH) {
    throw new LabelBarcodePayloadError(
      'PAYLOAD_TOO_LONG',
      'El código y la cantidad generan un código de barras demasiado largo.'
    );
  }

  return payload;
}

export function tryBuildLabelBarcodePayload(data: LabelBarcodeData): string | null {
  try {
    return buildLabelBarcodePayload(data);
  } catch {
    return null;
  }
}

/**
 * Parse a scanned DI1 barcode payload.
 * Unknown fields are rejected (strict policy for future scanners).
 */
export function parseLabelBarcodePayload(payload: string): ParsedLabelBarcode {
  const raw = payload.trim();
  if (!raw) {
    throw new LabelBarcodePayloadError('EMPTY_PAYLOAD', 'Payload vacío.');
  }

  const parts = raw.split('|');
  if (parts[0] !== LABEL_BARCODE_VERSION) {
    throw new LabelBarcodePayloadError('INVALID_VERSION', 'Versión de barcode no soportada.');
  }
  if (parts.length !== 3) {
    throw new LabelBarcodePayloadError('MALFORMED', 'Payload malformado.');
  }

  let codeRaw: string | null = null;
  let quantityRaw: string | null = null;

  for (let i = 1; i < parts.length; i += 1) {
    const segment = parts[i];
    const eq = segment.indexOf('=');
    if (eq <= 0) {
      throw new LabelBarcodePayloadError('MALFORMED', 'Campo de barcode malformado.');
    }
    const key = segment.slice(0, eq);
    const value = segment.slice(eq + 1);

    if (key === 'C') {
      if (codeRaw !== null) {
        throw new LabelBarcodePayloadError('DUPLICATE_FIELD', 'Campo C duplicado.');
      }
      codeRaw = value;
    } else if (key === 'Q') {
      if (quantityRaw !== null) {
        throw new LabelBarcodePayloadError('DUPLICATE_FIELD', 'Campo Q duplicado.');
      }
      quantityRaw = value;
    } else {
      throw new LabelBarcodePayloadError('UNKNOWN_FIELD', `Campo desconocido: ${key}.`);
    }
  }

  if (codeRaw === null) {
    throw new LabelBarcodePayloadError('MISSING_C', 'Falta el campo C.');
  }
  if (quantityRaw === null) {
    throw new LabelBarcodePayloadError('MISSING_Q', 'Falta el campo Q.');
  }

  let code: string;
  try {
    code = decodeURIComponent(codeRaw);
  } catch {
    throw new LabelBarcodePayloadError('INVALID_ESCAPE', 'Escape inválido en el código.');
  }

  const quantity = quantityRaw;
  if (!isValidLabelCode(code)) {
    throw new LabelBarcodePayloadError('INVALID_CODE', 'Código inválido en el payload.');
  }
  if (!isValidLabelQuantity(quantity)) {
    throw new LabelBarcodePayloadError('INVALID_QUANTITY', 'Cantidad inválida en el payload.');
  }

  return {
    version: LABEL_BARCODE_VERSION,
    code,
    quantity,
  };
}
