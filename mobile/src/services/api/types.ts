export interface AuthUserDto {
  readonly id: string;
  readonly username: string;
  readonly role: string;
  readonly client_id: string | null;
}

export interface LoginResponseDto {
  readonly access_token: string;
  readonly token_type: string;
  readonly expires_in: number;
  readonly refresh_token: string | null;
  readonly refresh_expires_in: number | null;
  readonly user: AuthUserDto;
}

export interface PageDto<T> {
  readonly items: T[];
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
}

export interface InventoryListItemDto {
  readonly id: string;
  readonly name: string;
  readonly status: string;
  readonly client_id: string | null;
  readonly created_at: string | null;
  readonly updated_at: string | null;
  readonly aisles_count: number;
  readonly pending_review_count: number;
  readonly last_activity_at: string | null;
  readonly processing_mode: string;
}

export interface CreateInventoryRequestDto {
  readonly name: string;
  readonly client_id: string;
  readonly processing_mode?: 'production' | 'test';
}

export interface InventoryResponseDto {
  readonly id: string;
  readonly name: string;
  readonly status: string;
  readonly processing_mode: string;
  readonly client_id: string | null;
  readonly created_at: string | null;
  readonly updated_at: string | null;
}

export interface ClientDto {
  readonly id: string;
  readonly name: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ClientSupplierDto {
  readonly id: string;
  readonly client_id: string;
  readonly name: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CreateAisleRequestDto {
  readonly code: string;
  readonly client_supplier_id?: string | null;
}

export interface AisleJobSummaryDto {
  readonly id: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly error_message?: string | null;
  readonly failure_code?: string | null;
  readonly failure_message?: string | null;
}

export interface AisleDto {
  readonly id: string;
  readonly inventory_id: string;
  readonly code: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly is_active?: boolean;
  readonly error_code?: string | null;
  readonly error_message?: string | null;
  readonly latest_job?: AisleJobSummaryDto | null;
  readonly assets_count: number;
  readonly positions_count: number;
  readonly pending_review_positions_count: number;
  readonly last_activity_at?: string | null;
}

/** GET /api/v3/config/upload-limits */
export interface UploadLimitsDto {
  readonly max_files_per_request: number;
  readonly max_file_size_bytes: number;
  readonly max_request_size_bytes: number;
  readonly upload_batch_concurrency: number;
  readonly retry_attempts: number;
  readonly retry_base_delay_ms: number;
}

export interface SourceAssetDto {
  readonly id: string;
  readonly aisle_id: string;
  readonly type: string;
  readonly original_filename: string;
  readonly storage_path: string;
  readonly mime_type: string;
  readonly uploaded_at: string;
  readonly file_size_bytes?: number | null;
}

export interface UploadAisleAssetUploadedDto {
  readonly client_file_id: string | null;
  readonly asset_id: string;
  readonly filename: string;
  readonly status: string;
}

export interface UploadAisleAssetErrorDto {
  readonly filename: string;
  readonly code: string;
  readonly detail: string;
  readonly file_index: number;
  readonly client_file_id: string | null;
}

export interface UploadAisleAssetsResponseDto {
  readonly assets: readonly SourceAssetDto[];
  readonly batch_id: string | null;
  readonly uploaded: readonly UploadAisleAssetUploadedDto[];
  readonly errors: readonly UploadAisleAssetErrorDto[];
}

export interface ProcessAisleResponseDto {
  readonly job_id: string;
}

export interface JobSummaryDto {
  readonly id: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly started_at?: string | null;
  readonly finished_at?: string | null;
  readonly error_message?: string | null;
  readonly failure_code?: string | null;
  readonly failure_message?: string | null;
  readonly current_stage?: string | null;
  readonly attempt_count?: number | null;
  readonly is_operational?: boolean;
}

export interface AisleStatusResponseDto {
  readonly aisle: AisleDto;
  readonly latest_job: JobSummaryDto | null;
  readonly operational_job_id: string | null;
  readonly recent_jobs: readonly JobSummaryDto[];
}

export interface AisleJobsResponseDto {
  readonly operational_job_id: string | null;
  readonly jobs: readonly JobSummaryDto[];
}

export interface MergeResultItemDto {
  readonly id: string;
  readonly position_id: string | null;
  readonly sku: string | null;
  readonly product_name: string | null;
  readonly merged_quantity: number;
  readonly normalized_label_ids: readonly string[];
  readonly review_required: boolean;
  readonly explanation_summary: string | null;
  readonly metadata: Record<string, unknown>;
  readonly created_at: string;
}

export interface MergeResultsResponseDto {
  readonly results: readonly MergeResultItemDto[];
  readonly result_job_id: string | null;
  readonly result_context_source: string;
}
