/**
 * Local-only photo lifecycle states (app side, not backend `SourceAsset` states).
 * These never leave the device and must not be sent to or created in the backend.
 */
export type PhotoStatus =
  | 'detected'
  | 'waiting_stability'
  | 'ready'
  | 'queued'
  | 'uploading'
  | 'confirmed'
  | 'retryable_error'
  | 'permanent_error'
  | 'excluded';

/** Local-only capture session lifecycle (app side). */
export type CaptureSessionStatus =
  | 'preparing'
  | 'active'
  | 'paused'
  | 'finishing'
  | 'waiting_uploads'
  | 'ready_to_process'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';
