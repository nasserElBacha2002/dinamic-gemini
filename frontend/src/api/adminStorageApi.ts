import { V3_ADMIN_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export type StorageCleanupTarget = 'remote' | 'local' | 'both';
export type StorageCleanupMode = 'dry_run' | 'delete';

export interface RemoteCleanupSection {
  provider: string;
  bucket?: string | null;
  prefix?: string | null;
  objects_found: number;
  objects_deleted: number;
  objects_skipped_protected?: number;
  objects_skipped_not_allowed?: number;
  bytes_found: number;
  bytes_deleted: number;
  protected_prefixes?: string[];
  allowed_prefixes?: string[];
  skipped: boolean;
  skip_reason?: string | null;
  errors: string[];
}

export interface LocalCleanupSection {
  output_dir: string;
  safe_roots: string[];
  allowed_roots?: string[];
  files_found: number;
  files_deleted: number;
  files_skipped_protected?: number;
  files_skipped_not_allowed?: number;
  bytes_found: number;
  bytes_deleted: number;
  protected_roots?: string[];
  skipped: boolean;
  skip_reason?: string | null;
  errors: string[];
}

export interface AdminStorageCleanupResponse {
  ok: boolean;
  mode: StorageCleanupMode;
  target: StorageCleanupTarget;
  remote: RemoteCleanupSection;
  local: LocalCleanupSection;
}

export interface AdminStorageCleanupRequest {
  target?: StorageCleanupTarget;
  mode?: StorageCleanupMode;
  confirm?: string;
  include_legacy_local?: boolean;
  include_pipeline_temp?: boolean;
  include_jobs?: boolean;
}

export async function postAdminStorageCleanup(
  body: AdminStorageCleanupRequest
): Promise<AdminStorageCleanupResponse> {
  return apiRequestJson<AdminStorageCleanupResponse>(
    `${API_BASE}${V3_ADMIN_BASE}/storage/cleanup`,
    { method: 'POST', body }
  );
}
