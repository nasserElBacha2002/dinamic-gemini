import { InventoryService } from '../src/features/inventories/inventoryService';
import { AisleService } from '../src/features/aisles/aisleService';
import { ProcessingService } from '../src/features/processing/processingService';
import { processingRunStore } from '../src/features/processing/processingRun';
import { createLogger } from '../src/core/logging';

jest.mock('@react-native-async-storage/async-storage', () => {
  const mem = new Map<string, string>();
  return {
    __esModule: true,
    default: {
      getItem: jest.fn(async (k: string) => mem.get(k) ?? null),
      setItem: jest.fn(async (k: string, v: string) => {
        mem.set(k, v);
      }),
      removeItem: jest.fn(async (k: string) => {
        mem.delete(k);
      }),
    },
  };
});

/**
 * Mocked service-chain against API contracts (not a device E2E).
 */
describe('operationalServices.mocked', () => {
  const api = {
    get: jest.fn(),
    post: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    processingRunStore.clear();
  });

  it('creates inventory → aisle → starts processing once with idempotency key', async () => {
    api.post
      .mockResolvedValueOnce({
        id: 'inv-1',
        name: 'Jornada',
        status: 'draft',
        processing_mode: 'production',
        client_id: 'client-1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      })
      .mockResolvedValueOnce({
        id: 'aisle-1',
        inventory_id: 'inv-1',
        code: 'P01',
        status: 'created',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        is_active: true,
        assets_count: 0,
        positions_count: 0,
        pending_review_positions_count: 0,
      })
      .mockResolvedValueOnce({ job_id: 'job-1' });

    api.get.mockImplementation(async (path: string) => {
      if (path.includes('/status')) {
        return {
          aisle: {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'P01',
            status: 'created',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            is_active: true,
            assets_count: 0,
            positions_count: 0,
            pending_review_positions_count: 0,
          },
          latest_job: null,
          recent_jobs: [],
          operational_job_id: null,
        };
      }
      if (path.includes('/inventories/inv-1') && !path.includes('/aisles')) {
        return {
          id: 'inv-1',
          name: 'Jornada',
          status: 'draft',
          processing_mode: 'production',
          client_id: 'client-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        };
      }
      return { items: [], page: 1, page_size: 50, total_items: 0, total_pages: 0 };
    });

    const inventories = new InventoryService(api as never);
    const aisles = new AisleService(api as never);
    const inventory = await inventories.create({ name: 'Jornada', clientId: 'client-1' });
    const aisle = await aisles.create({
      inventoryId: inventory.id,
      code: 'P01',
      clientSupplierId: 'sup-1',
    });

    const repo = {
      listPhotos: jest.fn().mockResolvedValue([
        { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
      ]),
      getSession: jest.fn().mockResolvedValue({
        id: 'session-1',
        inventory_id: inventory.id,
        aisle_id: aisle.id,
        backend_job_id: null,
      }),
      updateSessionStatus: jest.fn(),
      updateSessionUploadMeta: jest.fn(),
    };
    const jobs = {
      getByBackendJobId: jest.fn().mockResolvedValue(null),
      create: jest.fn(),
      listForSession: jest.fn().mockResolvedValue([]),
      getLatestForSession: jest.fn().mockResolvedValue(null),
      updatePoll: jest.fn(),
    };
    const uploadQueue = { refreshSessionReadiness: jest.fn().mockResolvedValue('ready') };
    const assetsApi = { listAssets: jest.fn().mockResolvedValue([{ id: 'asset-1' }]) };
    const processing = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      createLogger(() => undefined),
    );

    const start = await processing.startProcess('session-1');
    expect(start.ok).toBe(true);
    expect(start.jobId).toBe('job-1');
    const processCall = api.post.mock.calls.find(
      (c) => typeof c[0] === 'string' && String(c[0]).endsWith('/process'),
    );
    expect(processCall).toBeDefined();
    const body = processCall![1] as { idempotency_key: string };
    expect(body.idempotency_key).toMatch(/^mobile-process:session-1:/);
    expect(processCall![2]).toEqual({
      headers: { 'Idempotency-Key': body.idempotency_key },
    });
  });
});
