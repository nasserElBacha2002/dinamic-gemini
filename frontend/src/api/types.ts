/**
 * v3 API DTOs and error type — aligned with backend schemas.
 */

export const INVENTORY_STATUSES = [
  'draft',
  'processing',
  'in_review',
  'completed',
  'failed',
] as const;
export type InventoryStatus = (typeof INVENTORY_STATUSES)[number];

export const AISLE_STATUSES = [
  'created',
  'assets_uploaded',
  'queued',
  'processing',
  'processed',
  'in_review',
  'completed',
  'failed',
] as const;
export type AisleStatus = (typeof AISLE_STATUSES)[number];

/** Backend job status values (v3 API). */
export const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export interface Inventory {
  id: string;
  name: string;
  status: InventoryStatus | string;
  created_at?: string | null;
}

export interface Aisle {
  id: string;
  inventory_id: string;
  code: string;
  status: AisleStatus | string;
  created_at: string;
  updated_at: string;
  error_code?: string | null;
  error_message?: string | null;
  latest_job?: AisleJobSummary | null;
}

export interface AisleJobSummary {
  id: string;
  status: JobStatus | string;
  updated_at: string;
}

export interface ProcessAisleResponse {
  job_id: string;
}

export interface JobSummary {
  id: string;
  status: JobStatus | string;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
}

/** Source asset (photo/video) for an aisle — Épica 4. */
export interface SourceAssetSummary {
  id: string;
  aisle_id: string;
  type: 'photo' | 'video';
  original_filename: string;
  /** Backend storage path; not used by current UI (reserved for future evidence/media views). */
  storage_path: string;
  mime_type: string;
  uploaded_at: string;
}

/** Response for POST .../aisles/{aisle_id}/assets. */
export interface UploadAisleAssetsResponse {
  assets: SourceAssetSummary[];
}

export interface CreateInventoryRequest {
  name: string;
}

export interface CreateAisleRequest {
  code: string;
}

export interface ApiErrorDetail {
  detail?: string | unknown;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly data?: ApiErrorDetail
  ) {
    super(message);
    this.name = 'ApiError';
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}
