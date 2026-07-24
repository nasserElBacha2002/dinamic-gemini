import { ServerReprocessService } from '../src/features/serverReprocess/serverReprocessService';

describe('ServerReprocessService', () => {
  it('hides action when flag is off', () => {
    const service = new ServerReprocessService(
      {} as never,
      null,
      {
        mobileServerReprocess: false,
        mobileServerReprocessReview: false,
        serverReprocessOfflineQueue: false,
      },
    );
    expect(service.isActionVisible()).toBe(false);
    expect(service.isReviewVisible()).toBe(false);
  });

  it('shows action and review when flags are on', () => {
    const service = new ServerReprocessService(
      {} as never,
      null,
      {
        mobileServerReprocess: true,
        mobileServerReprocessReview: true,
        serverReprocessOfflineQueue: false,
      },
    );
    expect(service.isActionVisible()).toBe(true);
    expect(service.isReviewVisible()).toBe(true);
  });

  it('persists offline intent when offline queue enabled', async () => {
    const upsertPending = jest.fn(async () => undefined);
    const service = new ServerReprocessService(
      {
        requestReprocess: jest.fn(),
      } as never,
      { upsertPending } as never,
      {
        mobileServerReprocess: true,
        mobileServerReprocessReview: true,
        serverReprocessOfflineQueue: true,
      },
    );
    const result = await service.requestReprocess({
      inventoryId: 'i1',
      aisleId: 'a1',
      scopeType: 'FULL_AISLE',
      processingMode: 'CODE_SCAN',
      offline: true,
    });
    expect(result).toEqual(expect.objectContaining({ pending: true }));
    expect(upsertPending).toHaveBeenCalled();
  });
});
