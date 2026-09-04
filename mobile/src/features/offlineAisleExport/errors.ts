export type OfflineAisleExportErrorCode =
  | 'AISLE_NOT_FOUND'
  | 'AISLE_NOT_EXPORTABLE'
  | 'INVENTORY_NOT_FOUND'
  | 'SUPPLIER_NOT_FOUND'
  | 'CAPTURE_ID_DUPLICATED'
  | 'CAPTURE_AISLE_MISMATCH'
  | 'SUPPLIER_METADATA_INCOMPLETE'
  | 'RAW_EVIDENCE_MISSING'
  | 'PROFILE_METADATA_INCOMPLETE'
  | 'ASSET_MISSING'
  | 'PACKAGE_WRITE_FAILED'
  | 'PACKAGE_HASH_FAILED'
  | 'EXPORT_IN_PROGRESS'
  | 'NO_CAPTURES';

export class OfflineAisleExportError extends Error {
  readonly code: OfflineAisleExportErrorCode;

  constructor(code: OfflineAisleExportErrorCode, message: string) {
    super(`${code}: ${message}`);
    this.name = 'OfflineAisleExportError';
    this.code = code;
  }
}
