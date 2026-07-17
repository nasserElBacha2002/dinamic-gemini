/**
 * Unified inventory label code payload (QR + barcode + scanners).
 *
 * Primary format (v2 print):
 *   <internal_code>|<quantity>
 *   Example: 22294029014|234
 *
 * Backward compatible parse:
 *   - DI1|C=<urlencoded>|Q=<qty>  (previous barcode format)
 *   - plain internal code only   (quantity = null)
 */

export const INVENTORY_CODE_PAYLOAD_SEPARATOR = '|' as const;

/** Max trimmed internal code length (print + scan). */
export const INVENTORY_CODE_MAX_LENGTH = 48;

/**
 * Max encoded payload length for CODE128 in the enlarged printable barcode area.
 * Short `code|qty` payloads leave headroom; still reject silent clipping.
 */
export const INVENTORY_CODE_PAYLOAD_MAX_LENGTH = 72;

/** Positive integers 1–99999999; no leading zeros, decimals, or thousand separators. */
export const INVENTORY_QUANTITY_PATTERN = /^[1-9]\d{0,7}$/;

/** Legacy DI1 barcode version (still accepted by the parser). */
export const LEGACY_DI1_VERSION = 'DI1' as const;

export interface InventoryCodeData {
  code: string;
  quantity: string;
}

export interface ParsedInventoryCode {
  /** Primary printable format uses 'pipe'; DI1 scans report 'di1'; code-only → 'plain'. */
  readonly format: 'pipe' | 'di1' | 'plain';
  readonly internal_code: string;
  /** Null when an older code-only label was scanned. */
  readonly quantity: string | null;
}

export class InventoryCodePayloadError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'InventoryCodePayloadError';
    this.code = code;
  }
}

export function normalizeInventoryCode(value: string): string {
  return value.trim();
}

export function normalizeInventoryQuantity(value: string): string {
  return value.trim();
}

export function isValidInventoryCode(value: string): boolean {
  const normalized = normalizeInventoryCode(value);
  if (!normalized || normalized.length > INVENTORY_CODE_MAX_LENGTH) {
    return false;
  }
  // Pipe is the payload delimiter — reject embedded separators.
  if (normalized.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR)) {
    return false;
  }
  return true;
}

export function isValidInventoryQuantity(value: string): boolean {
  return INVENTORY_QUANTITY_PATTERN.test(normalizeInventoryQuantity(value));
}

/** Quiet-zone modules per side passed to JsBarcode `margin`. */
export const INVENTORY_BARCODE_QUIET_MODULES = 10;

/**
 * Default available barcode width in CSS px (~260mm at 96dpi).
 * Used when the DOM wrapper has not laid out yet.
 */
export const INVENTORY_BARCODE_DEFAULT_AVAILABLE_WIDTH_PX = Math.round((260 / 25.4) * 96);

/** Minimum module width (px) for drone-readable bars — never shrink below this to force a fit. */
export const INVENTORY_BARCODE_MIN_MODULE_WIDTH = 1.0;

/** Soft cap so extremely short payloads do not create absurdly thick bars. */
export const INVENTORY_BARCODE_MAX_MODULE_WIDTH = 6;

/**
 * Approximate CODE128 module count (Code Set B style) including quiet zones.
 * Used to size module width against the physical container before JsBarcode render.
 */
export function estimateCode128ModuleCount(
  payload: string,
  quietModules: number = INVENTORY_BARCODE_QUIET_MODULES
): number {
  const n = Math.max(1, payload.trim().length);
  // Start(11) + n*11 + checksum(11) + stop(13) + 2*quiet
  return 11 * n + 35 + 2 * quietModules;
}

/**
 * Module bar width for JsBarcode so the barcode fills `availableWidthPx`.
 * Returns null when filling the width would require modules thinner than the drone minimum
 * (caller should treat as a fit error — do not silently clip).
 */
export function inventoryBarcodeModuleWidth(
  payload: string,
  availableWidthPx: number = INVENTORY_BARCODE_DEFAULT_AVAILABLE_WIDTH_PX,
  options?: {
    quietModules?: number;
    minModuleWidth?: number;
    maxModuleWidth?: number;
  }
): number | null {
  const quiet = options?.quietModules ?? INVENTORY_BARCODE_QUIET_MODULES;
  const minW = options?.minModuleWidth ?? INVENTORY_BARCODE_MIN_MODULE_WIDTH;
  const maxW = options?.maxModuleWidth ?? INVENTORY_BARCODE_MAX_MODULE_WIDTH;
  const available = Number.isFinite(availableWidthPx) && availableWidthPx > 0 ? availableWidthPx : 0;
  if (!payload.trim() || available <= 0) {
    return null;
  }

  const modules = estimateCode128ModuleCount(payload, quiet);
  const raw = available / modules;
  if (raw < minW) {
    return null;
  }
  return Math.min(maxW, raw);
}

/** Build primary printable/scannable payload: code|quantity */
export function buildInventoryCodePayload({ code, quantity }: InventoryCodeData): string {
  const normalizedCode = normalizeInventoryCode(code);
  const normalizedQuantity = normalizeInventoryQuantity(quantity);

  if (!normalizedCode) {
    throw new InventoryCodePayloadError('EMPTY_CODE', 'El código interno es obligatorio.');
  }
  if (normalizedCode.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR)) {
    throw new InventoryCodePayloadError(
      'INVALID_CODE',
      'El código interno no puede contener el carácter "|".'
    );
  }
  if (normalizedCode.length > INVENTORY_CODE_MAX_LENGTH) {
    throw new InventoryCodePayloadError('CODE_TOO_LONG', 'El código interno es demasiado largo.');
  }
  if (!normalizedQuantity) {
    throw new InventoryCodePayloadError('EMPTY_QUANTITY', 'La cantidad total es obligatoria.');
  }
  if (!INVENTORY_QUANTITY_PATTERN.test(normalizedQuantity)) {
    throw new InventoryCodePayloadError(
      'INVALID_QUANTITY',
      'La cantidad debe ser un entero positivo sin decimales ni separadores.'
    );
  }

  const payload = `${normalizedCode}${INVENTORY_CODE_PAYLOAD_SEPARATOR}${normalizedQuantity}`;
  if (payload.length > INVENTORY_CODE_PAYLOAD_MAX_LENGTH) {
    throw new InventoryCodePayloadError(
      'PAYLOAD_TOO_LONG',
      'El código y la cantidad generan un payload demasiado largo.'
    );
  }
  return payload;
}

export function tryBuildInventoryCodePayload(data: InventoryCodeData): string | null {
  try {
    return buildInventoryCodePayload(data);
  } catch {
    return null;
  }
}

/**
 * Parse a scanned QR/barcode value.
 * Never throws for legacy plain codes — returns quantity null.
 * Throws only for clearly malformed structured payloads (DI1 / pipe with bad quantity).
 */
export function parseInventoryCodePayload(payload: string): ParsedInventoryCode {
  const raw = payload.trim();
  if (!raw) {
    throw new InventoryCodePayloadError('EMPTY_PAYLOAD', 'Payload vacío.');
  }

  if (raw.startsWith(`${LEGACY_DI1_VERSION}|`)) {
    return parseDi1Payload(raw);
  }

  const sep = raw.indexOf(INVENTORY_CODE_PAYLOAD_SEPARATOR);
  if (sep > 0 && sep < raw.length - 1 && !raw.includes('\n')) {
    const codePart = raw.slice(0, sep);
    const qtyPart = raw.slice(sep + 1);
    // Only treat as pipe payload when quantity looks like our quantity pattern
    // and there is exactly one separator (code cannot contain '|').
    if (
      !codePart.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR) &&
      !qtyPart.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR) &&
      INVENTORY_QUANTITY_PATTERN.test(qtyPart) &&
      isValidInventoryCode(codePart)
    ) {
      return {
        format: 'pipe',
        internal_code: normalizeInventoryCode(codePart),
        quantity: qtyPart,
      };
    }
  }

  // Legacy: code-only (or multiline human QR) — extract best-effort code, quantity null.
  const plainCode = extractPlainCode(raw);
  if (!plainCode) {
    throw new InventoryCodePayloadError('INVALID_CODE', 'No se pudo interpretar el código.');
  }
  return {
    format: 'plain',
    internal_code: plainCode,
    quantity: null,
  };
}

export function tryParseInventoryCodePayload(payload: string): ParsedInventoryCode | null {
  try {
    return parseInventoryCodePayload(payload);
  } catch {
    return null;
  }
}

function parseDi1Payload(raw: string): ParsedInventoryCode {
  const parts = raw.split('|');
  if (parts[0] !== LEGACY_DI1_VERSION || parts.length !== 3) {
    throw new InventoryCodePayloadError('MALFORMED', 'Payload DI1 malformado.');
  }

  let codeRaw: string | null = null;
  let quantityRaw: string | null = null;

  for (let i = 1; i < parts.length; i += 1) {
    const segment = parts[i];
    const eq = segment.indexOf('=');
    if (eq <= 0) {
      throw new InventoryCodePayloadError('MALFORMED', 'Campo DI1 malformado.');
    }
    const key = segment.slice(0, eq);
    const value = segment.slice(eq + 1);
    if (key === 'C') {
      if (codeRaw !== null) {
        throw new InventoryCodePayloadError('DUPLICATE_FIELD', 'Campo C duplicado.');
      }
      codeRaw = value;
    } else if (key === 'Q') {
      if (quantityRaw !== null) {
        throw new InventoryCodePayloadError('DUPLICATE_FIELD', 'Campo Q duplicado.');
      }
      quantityRaw = value;
    } else {
      throw new InventoryCodePayloadError('UNKNOWN_FIELD', `Campo desconocido: ${key}.`);
    }
  }

  if (codeRaw === null || quantityRaw === null) {
    throw new InventoryCodePayloadError('MALFORMED', 'Faltan campos C o Q en DI1.');
  }

  let code: string;
  try {
    code = decodeURIComponent(codeRaw);
  } catch {
    throw new InventoryCodePayloadError('INVALID_ESCAPE', 'Escape inválido en el código.');
  }

  if (!normalizeInventoryCode(code) || normalizeInventoryCode(code).length > INVENTORY_CODE_MAX_LENGTH) {
    throw new InventoryCodePayloadError('INVALID_CODE', 'Código inválido en el payload.');
  }
  if (!INVENTORY_QUANTITY_PATTERN.test(quantityRaw)) {
    throw new InventoryCodePayloadError('INVALID_QUANTITY', 'Cantidad inválida en el payload.');
  }

  return {
    format: 'di1',
    internal_code: normalizeInventoryCode(code),
    quantity: quantityRaw,
  };
}

function extractPlainCode(raw: string): string | null {
  // Prefer "Código interno: X" from legacy multiline QR text.
  const labeled = raw.match(/C[oó]digo interno:\s*(.+)/i);
  if (labeled?.[1]) {
    const code = normalizeInventoryCode(labeled[1].split('\n')[0] ?? '');
    if (code && !code.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR)) {
      return code.slice(0, INVENTORY_CODE_MAX_LENGTH);
    }
  }
  const firstLine = normalizeInventoryCode(raw.split('\n')[0] ?? '');
  if (!firstLine || firstLine.includes(INVENTORY_CODE_PAYLOAD_SEPARATOR)) {
    return null;
  }
  if (firstLine.length > INVENTORY_CODE_MAX_LENGTH) {
    return firstLine.slice(0, INVENTORY_CODE_MAX_LENGTH);
  }
  return firstLine;
}

/* -------------------------------------------------------------------------- */
/* Label-layer aliases (keep existing import paths stable)                    */
/* -------------------------------------------------------------------------- */

export const LABEL_BARCODE_VERSION = LEGACY_DI1_VERSION;
export const LABEL_CODE_MAX_LENGTH = INVENTORY_CODE_MAX_LENGTH;
export const LABEL_BARCODE_PAYLOAD_MAX_LENGTH = INVENTORY_CODE_PAYLOAD_MAX_LENGTH;
export const LABEL_QUANTITY_PATTERN = INVENTORY_QUANTITY_PATTERN;

export type LabelBarcodeData = InventoryCodeData;
export type ParsedLabelBarcode = {
  version: typeof LEGACY_DI1_VERSION | 'PIPE';
  code: string;
  quantity: string;
};

export const LabelBarcodePayloadError = InventoryCodePayloadError;

export const normalizeLabelCode = normalizeInventoryCode;
export const normalizeLabelQuantity = normalizeInventoryQuantity;
export const isValidLabelCode = isValidInventoryCode;
export const isValidLabelQuantity = isValidInventoryQuantity;
export const barcodeModuleWidth = inventoryBarcodeModuleWidth;

export function buildLabelBarcodePayload(data: LabelBarcodeData): string {
  return buildInventoryCodePayload(data);
}

export function tryBuildLabelBarcodePayload(data: LabelBarcodeData): string | null {
  return tryBuildInventoryCodePayload(data);
}

/**
 * Strict parse used by label tests / print path — requires quantity.
 * Accepts pipe and DI1; rejects plain code-only (no quantity).
 */
export function parseLabelBarcodePayload(payload: string): ParsedLabelBarcode {
  const parsed = parseInventoryCodePayload(payload);
  if (parsed.quantity === null) {
    throw new InventoryCodePayloadError(
      'MISSING_QUANTITY',
      'El payload no incluye cantidad.'
    );
  }
  return {
    version: parsed.format === 'di1' ? LEGACY_DI1_VERSION : 'PIPE',
    code: parsed.internal_code,
    quantity: parsed.quantity,
  };
}
