/** Local photo lifecycle for capture/review (app side only). */
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

/** Local-only capture session lifecycle (app side). */
export type CaptureSessionStatus =
  | 'preparing'
  | 'active'
  | 'paused'
  | 'finishing'
  | 'review'
  | 'completed'
  | 'failed'
  | 'cancelled';
