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
  readonly is_active: boolean;
  readonly error_code?: string | null;
  readonly error_message?: string | null;
  readonly latest_job?: AisleJobSummaryDto | null;
  readonly assets_count: number;
  readonly positions_count: number;
  readonly pending_review_positions_count: number;
  readonly last_activity_at?: string | null;
}

