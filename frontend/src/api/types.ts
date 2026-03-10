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

export interface AisleStatusResponse {
  aisle: Aisle;
  latest_job: JobSummary | null;
}

export interface JobSummary {
  id: string;
  status: JobStatus | string;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
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
