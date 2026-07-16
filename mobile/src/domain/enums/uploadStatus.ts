/** Local upload lifecycle for a photo (independent of capture stability status). */
export type PhotoUploadStatus =
  | 'not_queued'
  | 'queued'
  | 'preparing'
  | 'uploading'
  | 'uploaded'
  | 'retryable_error'
  | 'permanent_error'
  | 'remote_delete_pending'
  | 'remote_deleted'
  | 'excluded';

export type UploadBatchStatus =
  | 'pending'
  | 'running'
  | 'paused_offline'
  | 'paused_auth'
  | 'completed'
  | 'partial_error'
  | 'failed'
  | 'cancelled';

export type ProcessingJobLocalStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled'
  | 'unknown';

export const UPLOADABLE_PHOTO_STATUSES: readonly PhotoUploadStatus[] = [
  'queued',
  'preparing',
  'retryable_error',
];

export const TERMINAL_UPLOAD_SUCCESS: readonly PhotoUploadStatus[] = ['uploaded', 'remote_deleted'];
