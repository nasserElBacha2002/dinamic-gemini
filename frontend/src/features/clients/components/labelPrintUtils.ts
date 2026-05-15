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
