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
  // Phase 2 uploads while capturing: allow handoff to review/upload without a stuck active session.
  active: ['paused', 'finishing', 'review', 'uploading', 'failed', 'cancelled'],
  paused: ['active', 'finishing', 'review', 'uploading', 'failed', 'cancelled'],
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

/** Holds MediaStore listener / FGS — only one of these at a time. Paused/review do not block other aisles. */
export const CAPTURE_EXCLUSIVE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  'preparing',
  'active',
  'finishing',
];

/** @deprecated Prefer CAPTURE_EXCLUSIVE + activity listing. Kept for Fase 1 callers. */
export const OPEN_CAPTURE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  ...CAPTURE_EXCLUSIVE_SESSION_STATUSES,
  'paused',
  'review',
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
  if (s === 'running' || s === 'cancel_requested' || s === 'processing') {
    return 'running';
  }
  if (s === 'succeeded' || s === 'completed' || s === 'success') {
    return 'success';
  }
  if (s === 'failed' || s === 'timed_out' || s === 'error') {
    return 'failed';
  }
  if (s === 'canceled' || s === 'cancelled') {
    return 'cancelled';
  }
  return 'unknown';
}
