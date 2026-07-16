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
  finishing: ['review', 'failed', 'cancelled'],
  review: ['completed', 'cancelled'],
  completed: [],
  failed: ['paused', 'cancelled'],
  cancelled: [],
};

export const OPEN_CAPTURE_SESSION_STATUSES: readonly CaptureSessionStatus[] = [
  'preparing',
  'active',
  'paused',
  'finishing',
  'review',
  'failed',
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

export function isOpenCaptureSession(status: CaptureSessionStatus): boolean {
  return OPEN_CAPTURE_SESSION_STATUSES.includes(status);
}

export function isTerminalCaptureSession(status: CaptureSessionStatus): boolean {
  return status === 'completed' || status === 'cancelled';
}

