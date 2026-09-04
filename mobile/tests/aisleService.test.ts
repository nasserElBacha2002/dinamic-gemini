import { AisleService } from '../src/features/aisles/aisleService';
import { ApiError } from '../src/services/api/apiClient';

function remoteRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 'a1', inventory_id: 'inv-1', code: 'P01', status: 'created', active: 1,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    server_updated_at: '2026-01-01T00:00:00Z', synced_at: '2026-01-01T00:00:00Z',
    assets_count: 0, positions_count: 0, pending_review_positions_count: 0,
    client_supplier_id: 'sup-1', origin: 'REMOTE', sync_status: 'REMOTE_SYNCED',
    created_offline_at: null, ...overrides,
  };
}

describe('AisleService.create', () => {
  const api = {
    post: jest.fn(),
    get: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('rejects empty code', async () => {
    const service = new AisleService(api as never);
    await expect(service.create({ inventoryId: 'inv-1', code: ' ' })).rejects.toThrow('obligatorio');
  });

  it('posts aisle with supplier when provided', async () => {
    api.post.mockResolvedValue({
      id: 'a1',
      inventory_id: 'inv-1',
      code: 'P01',
      status: 'created',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      is_active: true,
      assets_count: 0,
      positions_count: 0,
      pending_review_positions_count: 0,
      client_supplier_id: 'sup-1',
    });
    const catalog = {
      getAisleById: jest.fn().mockResolvedValue(null),
      upsertRemoteAisle: jest.fn().mockResolvedValue(remoteRow()),
    };
    const resolver = {
      invalidate: jest.fn(),
      resolveForAisle: jest.fn().mockResolvedValue({
        item: { missingSupplierProfile: false, recognitionConfigNotReady: false },
        position: { missingSupplierProfile: false, recognitionConfigNotReady: false },
      }),
    };
    const service = new AisleService(
      api as never, undefined, catalog as never, undefined, undefined, undefined, undefined,
      resolver as never,
    );
    const aisle = await service.create({
      inventoryId: 'inv-1',
      code: 'P01',
      clientSupplierId: 'sup-1',
    });
    expect(api.post).toHaveBeenCalledWith('/api/v3/inventories/inv-1/aisles', {
      code: 'P01',
      client_supplier_id: 'sup-1',
    });
    expect(aisle.code).toBe('P01');
    expect(catalog.upsertRemoteAisle).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a1', client_supplier_id: 'sup-1' }),
      expect.any(String),
    );
    expect(resolver.resolveForAisle).toHaveBeenCalledWith('inv-1', 'a1');
  });

  it('does not resolve or return before the remote aisle is materialized', async () => {
    api.post.mockResolvedValue(remoteRow({ is_active: true }));
    let release!: () => void;
    const row = remoteRow();
    const write = new Promise<typeof row>((resolve) => { release = () => resolve(row); });
    const catalog = {
      getAisleById: jest.fn().mockResolvedValue(null),
      upsertRemoteAisle: jest.fn(() => write),
    };
    const resolver = {
      invalidate: jest.fn(),
      resolveForAisle: jest.fn().mockResolvedValue({
        item: { missingSupplierProfile: false, recognitionConfigNotReady: false },
        position: { missingSupplierProfile: false, recognitionConfigNotReady: false },
      }),
    };
    const service = new AisleService(
      api as never, undefined, catalog as never, undefined, undefined, undefined, undefined,
      resolver as never,
    );
    let completed = false;
    const creation = service.create({ inventoryId: 'inv-1', code: 'P01', clientSupplierId: 'sup-1' })
      .then((result) => { completed = true; return result; });
    await Promise.resolve();
    await Promise.resolve();
    expect(completed).toBe(false);
    expect(resolver.resolveForAisle).not.toHaveBeenCalled();
    release();
    await expect(creation).resolves.toMatchObject({ id: 'a1' });
    expect(resolver.resolveForAisle).toHaveBeenCalledTimes(1);
  });

  it('blocks capture handoff when local materialization fails', async () => {
    api.post.mockResolvedValue(remoteRow({ is_active: true }));
    const catalog = {
      getAisleById: jest.fn().mockResolvedValue(null),
      upsertRemoteAisle: jest.fn().mockRejectedValue(new Error('disk full')),
    };
    const service = new AisleService(api as never, undefined, catalog as never);
    await expect(service.create({ inventoryId: 'inv-1', code: 'P01', clientSupplierId: 'sup-1' }))
      .rejects.toMatchObject({ code: 'REMOTE_AISLE_MATERIALIZATION_FAILED' });
  });

  it('retries an already-created aisle locally without a duplicate POST', async () => {
    api.post.mockResolvedValue(remoteRow({ is_active: true }));
    const catalog = {
      getAisleById: jest.fn().mockResolvedValue(null),
      upsertRemoteAisle: jest.fn()
        .mockRejectedValueOnce(new Error('transient sqlite error'))
        .mockResolvedValueOnce(remoteRow()),
    };
    const service = new AisleService(api as never, undefined, catalog as never);
    const input = { inventoryId: 'inv-1', code: 'P01', clientSupplierId: 'sup-1' };
    await expect(service.create(input)).rejects.toMatchObject({
      code: 'REMOTE_AISLE_MATERIALIZATION_FAILED',
    });
    await expect(service.create(input)).resolves.toMatchObject({ id: 'a1' });
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(catalog.upsertRemoteAisle).toHaveBeenCalledTimes(2);
  });

  it('maps 403 to operational message', async () => {
    api.post.mockRejectedValue(new ApiError('forbidden', 403, 'FORBIDDEN'));
    const service = new AisleService(api as never);
    await expect(service.create({ inventoryId: 'inv-1', code: 'A' })).rejects.toThrow('permisos');
  });
});
