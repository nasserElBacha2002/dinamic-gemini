/**
 * Real producer wiring for onPhotoStable (not enqueueStablePhoto-only).
 */

import {
  allowOfflineUploadForPhotoStable,
  runPhotoStableProducers,
} from '../src/runtime/bootstrap/photoStableProducers';

describe('photoStableProducers wiring', () => {
  function mocks() {
    return {
      uploadQueue: {
        enqueuePhoto: jest.fn(async () => undefined),
        rescanPhotoForLocalReview: jest.fn(async () => undefined),
      },
      offlineAutoEnqueue: {
        onPhotoPersisted: jest.fn(async () => undefined),
      },
      exportPrepQueue: {
        enqueueStablePhoto: jest.fn(async () => undefined),
      },
    };
  }

  const baseFlags = {
    localCompletion: true,
    mobileCsvExport: true,
    mobileLocalCodeScan: true,
    mobileExportPrepQueue: true,
  };

  it.each([
    { policy: 'MANUAL' as const, status: 'active', offline: false },
    { policy: 'NOW' as const, status: 'active', offline: true },
    { policy: 'WHEN_CONNECTED' as const, status: 'active', offline: true },
    { policy: 'MANUAL' as const, status: 'uploading', offline: true },
    { policy: 'MANUAL' as const, status: 'upload_review', offline: true },
  ])(
    'policy=$policy status=$status → offline=$offline + always prep when queue present',
    async ({ policy, status, offline }) => {
      const m = mocks();
      await runPhotoStableProducers({
        sessionId: 's1',
        photoId: 'p1',
        flags: baseFlags,
        uploadQueue: m.uploadQueue,
        captureRepo: {
          getSession: async () => ({ upload_policy: policy, status }),
        },
        offlineAutoEnqueue: m.offlineAutoEnqueue,
        exportPrepQueue: m.exportPrepQueue,
      });
      expect(m.uploadQueue.enqueuePhoto).toHaveBeenCalledWith('s1', 'p1');
      expect(m.uploadQueue.enqueuePhoto).toHaveBeenCalledTimes(1);
      if (offline) {
        expect(m.offlineAutoEnqueue.onPhotoPersisted).toHaveBeenCalledWith('s1', 'p1');
      } else {
        expect(m.offlineAutoEnqueue.onPhotoPersisted).not.toHaveBeenCalled();
      }
      expect(m.exportPrepQueue.enqueueStablePhoto).toHaveBeenCalledWith('s1', 'p1');
      expect(m.uploadQueue.rescanPhotoForLocalReview).not.toHaveBeenCalled();
    },
  );

  it('flag off / no prep queue: MANUAL does not call prep; may rescan for local review', async () => {
    const m = mocks();
    await runPhotoStableProducers({
      sessionId: 's1',
      photoId: 'p1',
      flags: { ...baseFlags, mobileExportPrepQueue: false },
      uploadQueue: m.uploadQueue,
      captureRepo: {
        getSession: async () => ({ upload_policy: 'MANUAL', status: 'active' }),
      },
      offlineAutoEnqueue: m.offlineAutoEnqueue,
      exportPrepQueue: null,
    });
    expect(m.exportPrepQueue.enqueueStablePhoto).not.toHaveBeenCalled();
    expect(m.offlineAutoEnqueue.onPhotoPersisted).not.toHaveBeenCalled();
    expect(m.uploadQueue.rescanPhotoForLocalReview).toHaveBeenCalledWith('p1');
  });

  it('CSV export off still enqueues prep when queue is wired', async () => {
    const m = mocks();
    await runPhotoStableProducers({
      sessionId: 's1',
      photoId: 'p1',
      flags: { ...baseFlags, mobileCsvExport: false, localCompletion: false },
      uploadQueue: m.uploadQueue,
      captureRepo: {
        getSession: async () => ({ upload_policy: 'MANUAL', status: 'active' }),
      },
      offlineAutoEnqueue: m.offlineAutoEnqueue,
      exportPrepQueue: m.exportPrepQueue,
    });
    // Without local zip mode, offline upload is always allowed.
    expect(m.offlineAutoEnqueue.onPhotoPersisted).toHaveBeenCalled();
    expect(m.exportPrepQueue.enqueueStablePhoto).toHaveBeenCalledWith('s1', 'p1');
  });

  it('allowOfflineUploadForPhotoStable matches local-zip gate', () => {
    expect(
      allowOfflineUploadForPhotoStable({
        flags: { mobileCsvExport: true },
        uploadPolicy: 'MANUAL',
        sessionStatus: 'active',
      }),
    ).toBe(false);
    expect(
      allowOfflineUploadForPhotoStable({
        flags: { mobileCsvExport: true },
        uploadPolicy: 'NOW',
        sessionStatus: 'active',
      }),
    ).toBe(true);
  });
});
