import { AisleService } from '../src/features/aisles/aisleService';
import { ApiError } from '../src/services/api/apiClient';

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
    });
    const service = new AisleService(api as never);
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
  });

  it('maps 403 to operational message', async () => {
    api.post.mockRejectedValue(new ApiError('forbidden', 403, 'FORBIDDEN'));
    const service = new AisleService(api as never);
    await expect(service.create({ inventoryId: 'inv-1', code: 'A' })).rejects.toThrow('permisos');
  });
});
