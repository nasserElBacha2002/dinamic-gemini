/**
 * Separated photo lifecycle axes (Fase 3).
 * Persistence may still use `status` + `upload_status` columns; this module
 * documents and validates the four responsibilities without collapsing them.
 */

export type CaptureAxisStatus =
  | 'detected'
  | 'waiting_stability'
  | 'stable'
  | 'unstable'
  | 'undecodable'
  | 'rejected'
  | 'excluded';

export type StabilityAxisStatus = 'pending' | 'checking' | 'stable' | 'unstable' | 'undecodable' | 'skipped';

export type UploadAxisStatus =
  | 'not_queued'
  | 'queued'
  | 'preparing'
  | 'uploading'
  | 'uploaded'
  | 'retryable_error'
  | 'permanent_error'
  | 'excluded'
  | 'remote_deleted';

export type RemoteAxisStatus = 'none' | 'uploaded' | 'deleted' | 'unknown';

export interface PhotoLifecycleAxes {
  readonly capture: CaptureAxisStatus;
  readonly stability: StabilityAxisStatus;
  readonly upload: UploadAxisStatus;
  readonly remote: RemoteAxisStatus;
}

export function deriveStabilityFromCapture(capture: CaptureAxisStatus): StabilityAxisStatus {
  switch (capture) {
    case 'detected':
      return 'pending';
    case 'waiting_stability':
      return 'checking';
    case 'stable':
      return 'stable';
    case 'unstable':
      return 'unstable';
    case 'undecodable':
      return 'undecodable';
    case 'excluded':
    case 'rejected':
      return 'skipped';
    default:
      return 'pending';
  }
}

export function deriveRemoteFromUpload(upload: UploadAxisStatus): RemoteAxisStatus {
  if (upload === 'uploaded') {
    return 'uploaded';
  }
  if (upload === 'remote_deleted') {
    return 'deleted';
  }
  if (upload === 'not_queued' || upload === 'queued' || upload === 'preparing') {
    return 'none';
  }
  return 'unknown';
}

export function buildPhotoLifecycleAxes(
  capture: CaptureAxisStatus,
  upload: UploadAxisStatus,
): PhotoLifecycleAxes {
  return {
    capture,
    stability: deriveStabilityFromCapture(capture),
    upload,
    remote: deriveRemoteFromUpload(upload),
  };
}
