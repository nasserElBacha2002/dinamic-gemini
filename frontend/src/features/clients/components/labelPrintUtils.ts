export const LABEL_COPIES_MIN = 1;
export const LABEL_COPIES_MAX = 50;

export interface LabelSheetData {
  clientName: string;
  supplierName: string | null;
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
