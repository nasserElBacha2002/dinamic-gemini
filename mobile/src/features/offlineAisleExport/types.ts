import type { OFFLINE_AISLE_FORMAT, OFFLINE_AISLE_SCHEMA_VERSION } from './constants';

export type CaptureLabelKind = 'ITEM' | 'POSITION' | 'UNRECOGNIZED';
export type CaptureResultKind =
  | 'PRODUCT'
  | 'POSITION_ONLY'
  | 'PRODUCT_WITH_POSITION'
  | 'UNRECOGNIZED'
  | 'MANUAL_REVIEW';

export type PackageCompleteness = 'COMPLETE' | 'PARTIAL';

export interface OfflineAisleKindProvenance {
  readonly source: string;
  readonly client_supplier_id: string | null;
  readonly profile_id: string | null;
  readonly profile_version: number | null;
  readonly profile_ref: string | null;
  readonly raw_evidence: {
    readonly raw_payload: string | null;
    readonly raw_payload_sha256: string | null;
  };
}

export interface OfflineAisleItemResult {
  readonly label_id: string | null;
  readonly sku: string | null;
  readonly quantity: number | null;
}

export interface OfflineAislePositionResult {
  readonly position_id: string | null;
  readonly pallet: string | null;
  readonly side: string | null;
  readonly level: string | null;
}

export interface OfflineAisleCaptureV1 {
  readonly capture_id: string;
  readonly capture_session_id: string;
  readonly aisle_id: string;
  readonly client_file_id: string | null;
  readonly sequence_number: number | null;
  readonly created_at: string | null;
  readonly label_kind: CaptureLabelKind;
  readonly result_kind: CaptureResultKind;
  readonly status: string;
  readonly error_code: string | null;
  readonly requires_review: boolean;
  readonly recognitions: {
    readonly item: OfflineAisleKindProvenance | null;
    readonly position: OfflineAisleKindProvenance | null;
  };
  readonly result: {
    readonly product: OfflineAisleItemResult | null;
    readonly position: OfflineAislePositionResult | null;
  };
  readonly asset: {
    readonly included: boolean;
    readonly asset_id: string;
    readonly path: string | null;
    readonly mime_type: string | null;
    readonly size_bytes: number | null;
    readonly sha256: string | null;
    readonly asset_missing?: boolean;
  } | null;
  readonly recognition_profile_snapshot_json?: string | null;
}

export interface OfflineAisleProfileEntryV1 {
  readonly profile_ref: string;
  readonly label_kind: 'ITEM' | 'POSITION';
  readonly client_supplier_id: string | null;
  readonly source: string;
  readonly profile_id: string;
  readonly profile_version: number;
  readonly snapshot?: Record<string, unknown> | null;
}

export interface OfflineAisleManifestV1 {
  readonly format: typeof OFFLINE_AISLE_FORMAT;
  readonly schema_version: typeof OFFLINE_AISLE_SCHEMA_VERSION;
  readonly export_id: string;
  readonly created_at: string;
  readonly app_version: string;
  readonly inventory: {
    readonly id: string;
    readonly name: string;
    readonly client_id: string | null;
  };
  readonly aisle: {
    readonly id: string;
    readonly name: string;
    readonly origin: string;
    readonly sync_status: string;
    readonly operational_status: string;
  };
  readonly supplier: {
    readonly client_supplier_id: string | null;
    readonly name: string | null;
  };
  readonly capture_count: number;
  readonly asset_count: number;
  readonly include_assets: boolean;
  readonly completeness: PackageCompleteness;
  readonly integrity: {
    readonly algorithm: 'sha256';
    readonly files: Record<string, string>;
  };
}

export interface OfflineAisleDocumentV1 {
  readonly id: string;
  readonly inventory_id: string;
  readonly client_supplier_id: string | null;
  readonly name: string;
  readonly created_offline_at: string | null;
  readonly completed_at: string | null;
  readonly origin: string;
  readonly sync_status: string;
}
