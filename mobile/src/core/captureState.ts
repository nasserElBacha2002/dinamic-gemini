import type { CapturePhotoStatus, CaptureSessionStatus } from '../domain/enums/photoStatus';

const PHOTO_TRANSITIONS: Readonly<Record<CapturePhotoStatus, readonly CapturePhotoStatus[]>> = {
  detected: ['waiting_stability', 'rejected', 'excluded', 'unstable', 'undecodable'],
  waiting_stability: ['stable', 'unstable', 'undecodable', 'rejected', 'excluded'],
  stable: ['excluded'],
  unstable: ['waiting_stability', 'excluded'],
  undecodable: ['waiting_stability', 'excluded'],
  rejected: ['waiting_stability', 'excluded'],
  excluded: ['waiting_stability'],
};

const SESSION_TRANSITIONS: Readonly<Record<CaptureSessionStatus, readonly CaptureSessionStatus[]>> = {
  preparing: ['active', 'failed', 'cancelled'],
  active: ['paused', 'finishing', 'failed', 'cancelled'],
  paused: ['active', 'finishing', 'failed', 'cancelled'],
  finishing: ['review', 'uploading', 'failed', 'cancelled'],
  review: ['uploading', 'upload_review', 'ready_to_process', 'completed', 'cancelled', 'failed'],
  uploading: ['upload_review', 'ready_to_process', 'failed', 'cancelled'],
  upload_review: ['uploading', 'ready_to_process', 'failed', 'cancelled'],
  ready_to_process: ['processing', 'upload_review', 'failed', 'cancelled'],
  processing: ['completed', 'failed_processing', 'failed', 'cancelled'],
  completed: [],
  failed: ['paused', 'upload_review', 'cancelled'],
  failed_processing: ['ready_to_process', 'cancelled'],
  cancelled: [],
};

/** Blocks starting a new capture on this device. */
export const CAPTURE_EXCLUSIVE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  'preparing',
  'active',
  'paused',
  'finishing',
  'review',
];

/** @deprecated Prefer CAPTURE_EXCLUSIVE + activity listing. Kept for Fase 1 callers. */
export const OPEN_CAPTURE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  ...CAPTURE_EXCLUSIVE_SESSION_STATUSES,
  'uploading',
  'upload_review',
  'ready_to_process',
  'processing',
  'failed',
  'failed_processing',
];

export function canTransitionPhoto(
  from: CapturePhotoStatus,
  to: CapturePhotoStatus,
): boolean {
  return from === to || PHOTO_TRANSITIONS[from].includes(to);
}

export function canTransitionSession(
  from: CaptureSessionStatus,
  to: CaptureSessionStatus,
): boolean {
  return from === to || SESSION_TRANSITIONS[from].includes(to);
}

export function isCaptureExclusiveSession(status: CaptureSessionStatus): boolean {
  return CAPTURE_EXCLUSIVE_SESSION_STATUSES.includes(status);
}

export function isOpenCaptureSession(status: CaptureSessionStatus): boolean {
  return OPEN_CAPTURE_SESSION_STATUSES.includes(status);
}

export function isTerminalCaptureSession(status: CaptureSessionStatus): boolean {
  return status === 'completed' || status === 'cancelled';
}

export function mapRemoteJobStatus(remote: string): 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'unknown' {
  const s = remote.toLowerCase();
  if (s === 'queued' || s === 'starting') {
    return 'pending';
  }
  if (s === 'running' || s === 'cancel_requested') {
    return 'running';
  }
  if (s === 'succeeded') {
    return 'success';
  }
  if (s === 'failed' || s === 'timed_out') {
    return 'failed';
  }
  if (s === 'canceled' || s === 'cancelled') {
    return 'cancelled';
  }
  return 'unknown';
}
