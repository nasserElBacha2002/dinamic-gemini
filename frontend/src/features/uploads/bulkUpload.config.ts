/** Central FE upload limits — keep in sync with backend AppSettings / env defaults. */

export const UPLOAD_LIMITS = {
  /** Max files in one multipart HTTP request (not total selection). */
  maxFilesPerRequest: Number(import.meta.env.VITE_MAX_FILES_PER_UPLOAD_REQUEST ?? 10),
  /** Max bytes for a single file (fallback; prefer runtime GET /api/v3/config/upload-limits). */
  maxFileSizeBytes: Number(import.meta.env.VITE_MAX_UPLOAD_FILE_SIZE_MB ?? 500) * 1024 * 1024,
  /** Max total bytes in one multipart request (fallback; prefer runtime limits). */
  maxBytesPerRequest: Number(import.meta.env.VITE_MAX_UPLOAD_REQUEST_SIZE_MB ?? 1024) * 1024 * 1024,
  /** Max concurrent batch HTTP requests. */
  uploadConcurrency: Number(import.meta.env.VITE_UPLOAD_BATCH_CONCURRENCY ?? 2),
  /** Transient network retries — additional attempts after the first (0 = one request). */
  retryAttempts: Number(import.meta.env.VITE_UPLOAD_RETRY_ATTEMPTS ?? 3),
  retryBaseDelayMs: Number(import.meta.env.VITE_UPLOAD_RETRY_BASE_DELAY_MS ?? 1000),
  /** Soft timeout for one batch XHR (0 = no xhr timeout). */
  requestTimeoutMs: Number(import.meta.env.VITE_UPLOAD_REQUEST_TIMEOUT_MS ?? 0),
} as const;

/** @deprecated Use UPLOAD_LIMITS.maxFilesPerRequest — kept for older imports. */
export const MAX_FILES_PER_UPLOAD = UPLOAD_LIMITS.maxFilesPerRequest;

/** @deprecated Alias — per-request file count only. */
export const CAPTURE_STAGING_MAX_FILES_PER_REQUEST = UPLOAD_LIMITS.maxFilesPerRequest;
