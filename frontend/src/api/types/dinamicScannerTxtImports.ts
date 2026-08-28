import type { LocalCsvImportSummary } from './localInventoryPackages';

export interface DinamicScannerTxtImportResponse {
  aisle_code: string;
  aisle_id: string;
  aisle_created: boolean;
  aisle_will_be_created: boolean;
  positions_imported: number;
  products_imported: number;
  omitted_records: number;
  parse_warnings: string[];
  duplicate: boolean;
  csv_import: LocalCsvImportSummary;
}

export type ImportInventorySuccess =
  | { kind: 'zip'; data: import('./localInventoryPackages').LocalInventoryPackageResponse }
  | { kind: 'txt'; data: DinamicScannerTxtImportResponse };
