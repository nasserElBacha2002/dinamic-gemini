/**
 * Local spike photo lifecycle (Fase 0 only — not the full upload queue).
 */
export type SpikePhotoStatus =
  | 'waiting_stability'
  | 'stable'
  | 'unstable'
  | 'undecodable'
  | 'rejected';

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
