import type { CaptureService } from '../capture/captureService';
import type { ExportPrepRepository } from '../../database/repositories/exportPrepRepository';
import { isValidStagedSha256 } from '../../database/repositories/exportPrepRepository';
import type { ExportPrepQueue } from './exportPrepQueue';
import { stagingFileExists } from './exportStaging';

export interface ExportPrepPhotoCoordinatorDeps {
  readonly capture: CaptureService;
  readonly prepQueue: ExportPrepQueue;
  readonly prepRepo: ExportPrepRepository;
  readonly getSessionId: () => string | null;
  readonly resolvePhotoIdByAssetId: (
    sessionId: string,
    assetId: string,
  ) => Promise<string | null>;
}

/**
 * Coordinates capture exclude/reinclude with export-prep job state (single call path).
 */
export class ExportPrepPhotoCoordinator {
  constructor(private readonly deps: ExportPrepPhotoCoordinatorDeps) {}

  async excludeByAssetId(assetId: string): Promise<void> {
    const sessionId = this.deps.getSessionId();
    let photoId: string | null = null;
    if (sessionId) {
      photoId = await this.deps.resolvePhotoIdByAssetId(sessionId, assetId);
    }
    await this.deps.capture.exclude(assetId);
    if (photoId) {
      await this.deps.prepQueue.markPhotoExcluded(photoId);
    } else if (sessionId) {
      photoId = await this.deps.resolvePhotoIdByAssetId(sessionId, assetId);
      if (photoId) await this.deps.prepQueue.markPhotoExcluded(photoId);
    }
  }

  async reincorporateByAssetId(assetId: string): Promise<void> {
    const sessionId = this.deps.getSessionId();
    if (!sessionId) {
      await this.deps.capture.reincorporate(assetId);
      return;
    }
    const photoId = await this.deps.resolvePhotoIdByAssetId(sessionId, assetId);
    await this.deps.capture.reincorporate(assetId);
    if (!photoId) return;

    const job = await this.deps.prepRepo.getByPhotoId(photoId);
    if (!job) {
      return;
    }
    if (job.status !== 'EXCLUDED') {
      return;
    }

    const stagingOk =
      (await stagingFileExists(job.staging_uri)) && isValidStagedSha256(job.sha256);
    await this.deps.prepRepo.requeueFromExcluded(photoId);
    if (stagingOk) {
      const promoted = await this.deps.prepRepo.promoteQueuedToReadyIfComplete(photoId);
      if (!promoted) {
        this.deps.prepQueue.wake();
      }
    } else {
      this.deps.prepQueue.wake();
    }
  }
}
