import { InventoryService } from '../src/features/inventories/inventoryService';
import { ApiError } from '../src/services/api/apiClient';

describe('InventoryService.create', () => {
  const api = {
    post: jest.fn(),
    get: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('rejects empty name locally', async () => {
    const service = new InventoryService(api as never);
    await expect(service.create({ name: '  ', clientId: 'c1' })).rejects.toThrow('obligatorio');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates inventory with valid payload', async () => {
    api.post.mockResolvedValue({
      id: 'inv-1',
      name: 'Jornada',
      status: 'draft',
      processing_mode: 'production',
      client_id: 'c1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });
    const service = new InventoryService(api as never);
    const created = await service.create({ name: 'Jornada', clientId: 'c1' });
    expect(api.post).toHaveBeenCalledWith('/api/v3/inventories/', {
      name: 'Jornada',
      client_id: 'c1',
      processing_mode: 'production',
    });
    expect(created.id).toBe('inv-1');
    expect(created.aisles_count).toBe(0);
  });

  it('maps 403 to operational message', async () => {
    api.post.mockRejectedValue(new ApiError('forbidden', 403, 'FORBIDDEN'));
    const service = new InventoryService(api as never);
    await expect(service.create({ name: 'X', clientId: 'c1' })).rejects.toThrow('permisos');
  });
});
