export const LABEL_COPIES_MIN = 1;
export const LABEL_COPIES_MAX = 50;

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
