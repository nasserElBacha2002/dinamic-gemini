import { computeProcessingReadiness } from '../src/features/processing/processingReadiness';
import type { CapturePhotoRow } from '../src/database/schema/captureSchema';

function photo(uploadStatus: CapturePhotoRow['upload_status'], status: CapturePhotoRow['status'] = 'stable'): CapturePhotoRow {
  return {
    status,
    upload_status: uploadStatus,
    backend_asset_id: uploadStatus === 'uploaded' ? 'remote-1' : null,
  } as CapturePhotoRow;
}

describe('processingReadiness', () => {
  it('blocks when uploads are pending', () => {
    const readiness = computeProcessingReadiness([photo('uploading')], 'pending');
    expect(readiness.ready).toBe(false);
    expect(readiness.pendingPhotos).toBe(1);
  });

  it('is ready when all included photos are uploaded', () => {
    const readiness = computeProcessingReadiness([photo('uploaded'), photo('excluded', 'excluded')], 'ready');
    expect(readiness).toMatchObject({
      ready: true,
      includedPhotos: 1,
      uploadedPhotos: 1,
      pendingPhotos: 0,
      failedPhotos: 0,
      reason: null,
    });
  });
});
