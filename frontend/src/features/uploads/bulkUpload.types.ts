export type BulkUploadFileStatus =
  | 'pending'
  | 'uploading'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type UploadErrorCode =
  | 'FILE_TOO_LARGE'
  | 'REQUEST_TOO_LARGE'
  | 'TOO_MANY_FILES'
  | 'INVALID_MEDIA'
  | 'DUPLICATE_FILE'
  | 'STORAGE_ERROR'
  | 'DATABASE_ERROR'
  | 'TIMEOUT'
  | 'NETWORK_ERROR'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'SESSION_NOT_UPLOADABLE'
  | 'UNKNOWN';

export interface BulkUploadFileResult {
  clientId: string;
  file: File;
  status: BulkUploadFileStatus;
  progress: number;
  attempts: number;
  errorCode?: UploadErrorCode;
  errorMessage?: string;
  serverId?: string;
}

export interface BulkUploadBatchPlan {
  files: BulkUploadFileResult[];
  totalBytes: number;
}

export interface CreateUploadBatchesOptions {
  maxFilesPerBatch: number;
  maxBytesPerBatch: number;
  maxFileSizeBytes: number;
}

export interface BulkUploadProgressSnapshot {
  uploadBatchId: string;
  phase: 'preparing' | 'uploading' | 'processing' | 'completed' | 'completed_with_errors' | 'cancelled';
  files: BulkUploadFileResult[];
  completedCount: number;
  failedCount: number;
  cancelledCount: number;
  totalCount: number;
  uploadedBytes: number;
  totalBytes: number;
  progressPct: number;
  batchesCompleted: number;
  batchesTotal: number;
}

export interface BulkUploadRunResult {
  uploadBatchId: string;
  files: BulkUploadFileResult[];
  completedCount: number;
  failedCount: number;
  cancelledCount: number;
  uploadedBytes: number;
  totalBytes: number;
}

/** Per-file outcome returned by a single HTTP batch upload adapter. */
export interface BulkUploadServerFileOutcome {
  clientFileId: string;
  status: 'completed' | 'failed';
  serverId?: string;
  code?: string;
  message?: string;
}

export interface BulkUploadServerBatchResult {
  outcomes: BulkUploadServerFileOutcome[];
}

export type BulkBatchUploader = (args: {
  uploadBatchId: string;
  files: BulkUploadFileResult[];
  signal: AbortSignal;
  onByteProgress: (bytesLoadedInBatch: number, bytesTotalInBatch: number) => void;
}) => Promise<BulkUploadServerBatchResult>;
