/** Offline recognition config bundle — mirrors backend OfflineRecognitionBundleResponse. */

export const OFFLINE_RECOGNITION_BUNDLE_SCHEMA_VERSION = 1;

export interface OfflineAisleRecognitionConfigDto {
  aisle_id: string;
  aisle_code?: string | null;
  client_supplier_id?: string | null;
  item_profile_source_override?: 'DINAMIC' | 'SUPPLIER' | null;
  position_profile_source_override?: 'DINAMIC' | 'SUPPLIER' | null;
  effective_item_source: 'DINAMIC' | 'SUPPLIER';
  effective_position_source: 'DINAMIC' | 'SUPPLIER';
}

export interface OfflineSupplierRecognitionConfigDto {
  client_supplier_id: string;
  item_source: 'DINAMIC' | 'SUPPLIER';
  position_source: 'DINAMIC' | 'SUPPLIER';
}

export interface OfflineRecognitionProfileDto {
  client_supplier_id: string;
  label_kind: 'ITEM' | 'POSITION';
  source: 'SUPPLIER';
  profile_id: string;
  profile_version: number;
  configuration_schema_version: number;
  recognition_mode?: string | null;
  semantic_type?: string | null;
  configuration: Record<string, unknown>;
}

export interface OfflineRecognitionBundleDto {
  bundle_schema_version: number;
  inventory_id: string;
  client_id: string;
  generated_at: string;
  aisles: OfflineAisleRecognitionConfigDto[];
  suppliers?: OfflineSupplierRecognitionConfigDto[];
  profiles: OfflineRecognitionProfileDto[];
  bundle_revision?: string | null;
}

export class IncompatibleOfflineBundleError extends Error {
  readonly code = 'INCOMPATIBLE_BUNDLE_SCHEMA';
  constructor(version: number) {
    super(`Unsupported offline recognition bundle_schema_version: ${version}`);
  }
}

export function assertCompatibleBundle(bundle: OfflineRecognitionBundleDto): void {
  const v = Number(bundle.bundle_schema_version);
  if (!Number.isFinite(v) || v !== OFFLINE_RECOGNITION_BUNDLE_SCHEMA_VERSION) {
    throw new IncompatibleOfflineBundleError(v);
  }
}
