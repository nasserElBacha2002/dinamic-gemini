/** Runtime upload limits from backend with local defaults as fallback. */
import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../../api/request';
import { UPLOAD_LIMITS } from './bulkUpload.config';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface UploadLimitsDto {
  max_files_per_request: number;
  max_file_size_bytes: number;
  max_request_size_bytes: number;
  upload_batch_concurrency: number;
  /** Additional retries after the initial attempt (0 = one request total). */
  retry_attempts: number;
  retry_base_delay_ms: number;
}

export interface ResolvedUploadLimits {
  maxFilesPerRequest: number;
  maxFileSizeBytes: number;
  maxBytesPerRequest: number;
  uploadConcurrency: number;
  /** Additional retries after the initial attempt (0 = one request total). */
  retryAttempts: number;
  retryBaseDelayMs: number;
  source: 'backend' | 'fallback';
}

export async function fetchUploadLimits(): Promise<UploadLimitsDto> {
  return apiRequestJson<UploadLimitsDto>(`${API_BASE}/api/v3/config/upload-limits`);
}

function fromDto(dto: UploadLimitsDto): ResolvedUploadLimits {
  return {
    maxFilesPerRequest: dto.max_files_per_request,
    maxFileSizeBytes: dto.max_file_size_bytes,
    maxBytesPerRequest: dto.max_request_size_bytes,
    uploadConcurrency: dto.upload_batch_concurrency,
    retryAttempts: dto.retry_attempts,
    retryBaseDelayMs: dto.retry_base_delay_ms,
    source: 'backend',
  };
}

function fallbackLimits(log = false): ResolvedUploadLimits {
  if (log && import.meta.env.DEV) {
    console.info('[uploads] Using local UPLOAD_LIMITS fallback (backend config unavailable)');
  }
  return {
    maxFilesPerRequest: UPLOAD_LIMITS.maxFilesPerRequest,
    maxFileSizeBytes: UPLOAD_LIMITS.maxFileSizeBytes,
    maxBytesPerRequest: UPLOAD_LIMITS.maxBytesPerRequest,
    uploadConcurrency: UPLOAD_LIMITS.uploadConcurrency,
    retryAttempts: UPLOAD_LIMITS.retryAttempts,
    retryBaseDelayMs: UPLOAD_LIMITS.retryBaseDelayMs,
    source: 'fallback',
  };
}

export function useUploadLimits(): ResolvedUploadLimits {
  const query = useQuery({
    queryKey: ['config', 'upload-limits'],
    queryFn: fetchUploadLimits,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  if (query.data) {
    return fromDto(query.data);
  }
  return fallbackLimits(Boolean(query.isError));
}
