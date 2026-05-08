/**
 * API request DTOs — request body contracts sent to the backend.
 */

import type {
  ClientStatus,
  ClientSupplierStatus,
  InventoryProcessingMode,
  ReviewActionType,
} from './shared';

export interface CreateInventoryRequest {
  name: string;
  /** Defaults to production (real operational mode). */
  processing_mode?: InventoryProcessingMode;
  /** Optional association to a client; omitted/null preserves legacy behavior. */
  client_id?: string | null;
}

export interface CreateAisleRequest {
  code: string;
  client_supplier_id?: string | null;
}

export interface CreateClientRequest {
  name: string;
  status?: ClientStatus;
}

export interface CreateClientSupplierRequest {
  name: string;
  status?: ClientSupplierStatus;
}

/** Multipart POST …/clients/{clientId}/suppliers/{supplierId}/reference-images — built client-side as FormData. */
export interface UploadSupplierReferenceImagesRequest {
  files: File[];
  label?: string;
  description?: string;
}

export interface CreateSupplierPromptConfigRequest {
  provider_name: string;
  model_name?: string | null;
  instructions_text: string;
  activate: boolean;
}

export interface CreateGlobalPromptConfigRequest {
  instructions_text: string;
  activate: boolean;
}

/** Request body for POST .../positions/{position_id}/reviews. */
export interface ReviewActionRequest {
  action_type: ReviewActionType;
  product_id?: string | null;
  corrected_quantity?: number | null;
  sku?: string | null;
  description?: string | null;
  position_code?: string | null;
  /** Required when ``position.job_id`` is set; omit entirely for legacy rows (preferred over null). */
  job_id?: string | null;
}

/** Request body for POST .../benchmark/compare-many. */
export interface AisleBenchmarkCompareManyRequest {
  job_ids: string[];
  baseline_job_id: string;
  include_diff_rows?: boolean;
  max_diff_rows?: number;
}
