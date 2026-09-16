/**
 * Independent producers wired from CaptureService.onPhotoStable.
 * Export prep is never gated on upload policy; offline upload is.
 */

export type PhotoStableUploadPolicy = 'MANUAL' | 'NOW' | 'WHEN_CONNECTED' | string | null | undefined;

export interface PhotoStableProducerFlags {
  readonly localCompletion?: boolean;
  readonly mobileCsvExport?: boolean;
  readonly mobileLocalCodeScan?: boolean;
  readonly mobileExportPrepQueue?: boolean;
}

export interface PhotoStableProducerDeps {
  readonly sessionId: string;
  readonly photoId: string;
  readonly flags: PhotoStableProducerFlags;
  readonly uploadQueue: {
    enqueuePhoto(sessionId: string, photoId: string): Promise<unknown>;
    rescanPhotoForLocalReview?(photoId: string): Promise<unknown>;
  };
  readonly captureRepo: {
    getSession(sessionId: string): Promise<{
      upload_policy?: PhotoStableUploadPolicy;
      status?: string | null;
    } | null>;
  };
  readonly offlineAutoEnqueue?: {
    onPhotoPersisted(sessionId: string, photoId: string): Promise<unknown>;
  } | null;
  readonly exportPrepQueue?: {
    enqueueStablePhoto(sessionId: string, photoId: string): Promise<void>;
  } | null;
}

export function allowOfflineUploadForPhotoStable(input: {
  readonly flags: PhotoStableProducerFlags;
  readonly uploadPolicy: PhotoStableUploadPolicy;
  readonly sessionStatus: string | null | undefined;
}): boolean {
  const localZipMode =
    input.flags.localCompletion === true || input.flags.mobileCsvExport === true;
  const policy = input.uploadPolicy;
  const status = input.sessionStatus;
  return (
    !localZipMode ||
    policy === 'NOW' ||
    policy === 'WHEN_CONNECTED' ||
    status === 'uploading' ||
    status === 'upload_review'
  );
}

/**
 * Runs upload enqueue + optional offline auto-enqueue + independent export-prep enqueue.
 * Callers must await the returned Promise (CaptureService does).
 * Phase 2 does **not** drain the prep queue; finish only awaits this enqueue work.
 */
export async function runPhotoStableProducers(deps: PhotoStableProducerDeps): Promise<void> {
  await deps.uploadQueue.enqueuePhoto(deps.sessionId, deps.photoId);
  const session = await deps.captureRepo.getSession(deps.sessionId);
  const allowOfflineUpload = allowOfflineUploadForPhotoStable({
    flags: deps.flags,
    uploadPolicy: session?.upload_policy,
    sessionStatus: session?.status,
  });
  if (allowOfflineUpload && deps.offlineAutoEnqueue) {
    await deps.offlineAutoEnqueue.onPhotoPersisted(deps.sessionId, deps.photoId);
  }
  if (deps.exportPrepQueue) {
    await deps.exportPrepQueue.enqueueStablePhoto(deps.sessionId, deps.photoId);
  } else if (
    !allowOfflineUpload &&
    (deps.flags.mobileLocalCodeScan === true ||
      deps.flags.mobileCsvExport !== false ||
      deps.flags.localCompletion === true)
  ) {
    await deps.uploadQueue.rescanPhotoForLocalReview?.(deps.photoId)?.catch(() => undefined);
  }
}
