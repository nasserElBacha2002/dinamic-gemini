/** Local inventory ZIP package import contract (aligned with backend schemas). */

export interface LocalCsvImportRowSummary {
  row_number: number;
  aisle_id: string;
  capture_photo_id: string;
  status: string;
  validation_errors: string[];
  validation_warnings: string[];
  productive_result_id: string | null;
}

export interface LocalCsvImportSummary {
  import_id: string;
  export_id: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  rows: LocalCsvImportRowSummary[];
}

export interface LocalInventoryPackagePhotoSummary {
  capture_photo_id: string;
  client_file_id: string;
  sequence_number: number | null;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  width: number | null;
  height: number | null;
  asset_variant: string;
  source_asset_id: string | null;
}

export interface LocalInventoryPackageResponse {
  package_id: string;
  export_id: string;
  inventory_id: string;
  csv_import_id: string;
  package_kind: string;
  package_version: number;
  status: string;
  expected_photo_count: number;
  included_photo_count: number;
  package_checksum_sha256: string | null;
  csv_checksum_sha256: string;
  aisle_id: string | null;
  capture_session_id: string | null;
  freeze_id: string | null;
  duplicate: boolean;
  created_at: string;
  confirmed_at: string | null;
  confirmed_by_user_id: string | null;
  photos: LocalInventoryPackagePhotoSummary[];
  csv_import: LocalCsvImportSummary | null;
}
