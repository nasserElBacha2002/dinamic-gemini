/** Local photo lifecycle for capture/review (app side only). Independent of upload_status. */
export type CapturePhotoStatus =
  | 'detected'
  | 'waiting_stability'
  | 'stable'
  | 'unstable'
  | 'undecodable'
  | 'rejected'
  | 'excluded';

/** @deprecated Use CapturePhotoStatus. */
export type SpikePhotoStatus = CapturePhotoStatus;

/**
 * Capture + post-capture session lifecycle.
 * Fase 1 statuses kept; Fase 2 adds upload/processing states.
 * Only CAPTURE_EXCLUSIVE statuses block starting another capture.
 */
export type CaptureSessionStatus =
  | 'preparing'
  | 'active'
  | 'paused'
  | 'finishing'
  | 'review'
  | 'uploading'
  | 'upload_review'
  | 'ready_to_process'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'failed_processing'
  | 'cancelled';
