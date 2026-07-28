/**
 * Auto-enqueue critical intentions into offline_operations when the flag is on.
 */

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { Logger } from '../../core/logging';
import { hashPayloadFingerprint } from '../../core/payloadFingerprint';
import type { OfflineOperationFacade } from './offlineOperationBridge';
import type { OfflineOperationScheduler } from './offlineOperationScheduler';

export function createOfflineAutoEnqueue(input: {
  readonly enabled: boolean;
  readonly facade: OfflineOperationFacade | null;
  readonly scheduler: OfflineOperationScheduler | null;
  readonly capture: CaptureRepository;
  readonly logger: Logger;
}) {
  const wake = () => {
    void input.scheduler?.tick();
  };

  return {
    async onPhotoPersisted(sessionId: string, photoId: string): Promise<void> {
      if (!input.enabled || !input.facade) {
        return;
      }
      try {
        const session = await input.capture.getSession(sessionId);
        const photo = await input.capture.getPhotoById(photoId);
        if (!session || !photo) {
          return;
        }
        const sha = hashPayloadFingerprint(
          `${photo.id}:${photo.uri}:${photo.upload_size ?? photo.size ?? 0}`,
        );
        await input.facade.enqueueUploadAsset({
          sessionId,
          inventoryId: session.inventory_id,
          aisleId: session.aisle_id,
          capturePhotoId: photo.id,
          assetId: photo.client_file_id || photo.id,
          localFilePath: photo.local_transform_uri || photo.uri,
          sha256: sha.replace(/^sha256:/, ''),
          preparedMimeType: photo.mime_type || 'image/jpeg',
          byteSize: photo.upload_size ?? photo.size ?? 0,
        });
        wake();
      } catch (error) {
        input.logger.warn('recovery', {
          where: 'offline_auto_enqueue_upload',
          message: error instanceof Error ? error.message : String(error),
        });
      }
    },

    async onResultConfirmed(inputConfirm: {
      readonly resultId: string;
      readonly capturePhotoId: string;
      readonly sessionId: string;
      readonly inventoryId: string;
      readonly aisleId: string;
      readonly contentHash: string;
    }): Promise<void> {
      if (!input.enabled || !input.facade) {
        return;
      }
      try {
        await input.facade.enqueueSyncAuthoritativeResult({
          resultId: inputConfirm.resultId,
          contentHash: inputConfirm.contentHash,
          capturePhotoId: inputConfirm.capturePhotoId,
          sessionId: inputConfirm.sessionId,
          inventoryId: inputConfirm.inventoryId,
          aisleId: inputConfirm.aisleId,
        });
        wake();
      } catch (error) {
        input.logger.warn('recovery', {
          where: 'offline_auto_enqueue_sync',
          message: error instanceof Error ? error.message : String(error),
        });
      }
    },
  };
}
