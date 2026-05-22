export const LABEL_COPIES_MIN = 1;
export const LABEL_COPIES_MAX = 50;

/** Internal code length at or above which the label uses compact typography. */
export const LABEL_CODE_ADAPTIVE_LONG_MIN_LENGTH = 20;

/** Internal code length at or above which the label uses extra-compact typography. */
export const LABEL_CODE_ADAPTIVE_XLONG_MIN_LENGTH = 32;

/** Printed on every warehouse label (Spanish, fixed for warehouse/CV readability). */
export const LABEL_PRINT_TITLE = 'ETIQUETA PARA INVENTARIO DE MERCADERÍA EN PALLETS';

export interface LabelSheetData {
  clientName: string;
  supplierName: string | null;
  countedBy: string | null;
  code: string;
  quantity: string;
  lot: string | null;
  expiry: string | null;
  description: string | null;
  observations: string | null;
  copies: number;
}

export function clampLabelCopies(value: number): number {
  if (!Number.isFinite(value)) return LABEL_COPIES_MIN;
  return Math.min(LABEL_COPIES_MAX, Math.max(LABEL_COPIES_MIN, Math.floor(value)));
}

/** Short date for label header (DD/MM). */
export function formatShortLabelDate(date: Date = new Date()): string {
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${day}/${month}`;
}

/** Sanitize one segment for suggested print/PDF filename (document.title). */
export function sanitizeLabelFilenameSegment(value: string, fallback: string): string {
  const normalized = value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

  return normalized || fallback;
}

/** ISO date for print filename suffix (YYYY-MM-DD). */
export function formatLabelFilenameDate(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** CSS classes for the printed internal code value (adaptive size for long codes). */
export function getLabelCodeMainValueClassName(code: string): string {
  const length = code.trim().length;
  const classes = ['label-primary-value', 'label-code-main-value'];

  if (length >= LABEL_CODE_ADAPTIVE_XLONG_MIN_LENGTH) {
    classes.push('label-code-main-value--xlong');
  } else if (length >= LABEL_CODE_ADAPTIVE_LONG_MIN_LENGTH) {
    classes.push('label-code-main-value--long');
  }

  return classes.join(' ');
}

/** Human-readable multiline text for the single per-label QR (plain scan, not JSON). */
export function buildLabelQrText(data: Omit<LabelSheetData, 'copies'>, date: Date = new Date()): string {
  const lines = [
    'ETIQUETA DINAMIC INVENTORY',
    `Cliente: ${data.clientName.trim() || '—'}`,
  ];

  const supplier = data.supplierName?.trim();
  if (supplier) lines.push(`Proveedor: ${supplier}`);

  const countedBy = data.countedBy?.trim();
  if (countedBy) lines.push(`Contado por: ${countedBy}`);

  lines.push(`Código interno: ${data.code.trim()}`);
  lines.push(`Cant. total: ${data.quantity.trim()}`);

  const lot = data.lot?.trim();
  if (lot) lines.push(`Lote: ${lot}`);

  const expiry = data.expiry?.trim();
  if (expiry) lines.push(`VTO: ${expiry}`);

  const description = data.description?.trim();
  if (description) lines.push(`Descripción: ${description}`);

  const observations = data.observations?.trim();
  if (observations) lines.push(`Observaciones: ${observations}`);

  lines.push(`Generado: ${formatLabelFilenameDate(date)}`);

  return lines.join('\n');
}

/** Suggested PDF filename base: cliente-codigo-cantidad-fecha */
export function buildLabelPrintFilename(
  data: Pick<LabelSheetData, 'clientName' | 'code' | 'quantity'>,
  date: Date = new Date()
): string {
  return [
    sanitizeLabelFilenameSegment(data.clientName, 'cliente'),
    sanitizeLabelFilenameSegment(data.code, 'codigo'),
    sanitizeLabelFilenameSegment(data.quantity, 'cantidad'),
    formatLabelFilenameDate(date),
  ].join('-');
}
