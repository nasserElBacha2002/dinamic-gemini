import { AisleRevisionService } from '../src/features/aisleRevision/aisleRevisionService';

describe('AisleRevisionService', () => {
  const baseFlags = {
    mobileAisleRevisions: false,
    mobileAisleHistory: false,
    serverAisleRevisions: false,
    serverAisleRollback: false,
  };

  it('hides action and history when flags are off', () => {
    const service = new AisleRevisionService({} as never, null, null, baseFlags);
    expect(service.isActionVisible()).toBe(false);
    expect(service.isHistoryVisible()).toBe(false);
    expect(service.isRollbackVisible()).toBe(false);
  });

  it('shows action when mobile revision flag is on', () => {
    const service = new AisleRevisionService(
      {} as never,
      null,
      null,
      { ...baseFlags, mobileAisleRevisions: true },
    );
    expect(service.isActionVisible()).toBe(true);
    expect(service.isHistoryVisible()).toBe(false);
  });

  it('shows history and rollback when respective flags are on', () => {
    const service = new AisleRevisionService(
      {} as never,
      null,
      null,
      {
        ...baseFlags,
        mobileAisleHistory: true,
        serverAisleRollback: true,
      },
    );
    expect(service.isHistoryVisible()).toBe(true);
    expect(service.isRollbackVisible()).toBe(true);
  });

  it('saves local draft when offline and server revisions disabled', async () => {
    const upsertDraft = jest.fn(async () => undefined);
    const connectivity = {
      getState: () => 'offline' as const,
      subscribe: () => () => undefined,
    };
    const service = new AisleRevisionService(
      { createRevision: jest.fn() } as never,
      { upsertDraft } as never,
      connectivity,
      { ...baseFlags, mobileAisleRevisions: true, serverAisleRevisions: false },
    );
    const result = await service.createRevision({
      inventoryId: 'inv1',
      aisleId: 'aisle1',
      revisionType: 'MANUAL_CORRECTION',
      reason: 'test',
      requestedBy: 'user1',
    });
    expect(result).toEqual(expect.objectContaining({ local: true }));
    expect(upsertDraft).toHaveBeenCalled();
  });

  it('blocks apply when offline', async () => {
    const connectivity = {
      getState: () => 'offline' as const,
      subscribe: () => () => undefined,
    };
    const service = new AisleRevisionService(
      { apply: jest.fn() } as never,
      null,
      connectivity,
      { ...baseFlags, mobileAisleRevisions: true, serverAisleRevisions: true },
    );
    await expect(
      service.applyRevision({
        inventoryId: 'inv1',
        aisleId: 'aisle1',
        revisionId: 'rev1',
        expectedBaseFinalizationId: 'fin1',
        appliedBy: 'user1',
      }),
    ).rejects.toThrow(/conexión/i);
  });
});
