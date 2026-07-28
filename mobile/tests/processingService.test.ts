import { processingRunStore, buildProcessRunIdempotencyKey } from '../src/features/processing/processingRun';
import { processIdempotencyKey, ProcessingService } from '../src/features/processing/processingService';
import { createLogger } from '../src/core/logging';
import { ApiError } from '../src/services/api/apiClient';

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

describe('ProcessingService', () => {
  const api = { get: jest.fn(), post: jest.fn() };
  const repo = {
    listPhotos: jest.fn(),
    getSession: jest.fn(),
    updateSessionStatus: jest.fn(),
    updateSessionUploadMeta: jest.fn(),
    setPreparationProcessingMode: jest.fn(async () => undefined),
  };
  const jobs = {
    getByBackendJobId: jest.fn(),
    create: jest.fn(),
    listForSession: jest.fn(),
    getLatestForSession: jest.fn(),
    updatePoll: jest.fn(),
  };
  const uploadQueue = {
    refreshSessionReadiness: jest.fn(),
  };
  const assetsApi = { listAssets: jest.fn() };
  const logger = createLogger(() => undefined);

  beforeEach(() => {
    jest.clearAllMocks();
    processingRunStore.clear();
  });

  it('builds run-scoped idempotency keys', () => {
    expect(processIdempotencyKey('session-1', 'run-a')).toBe('mobile-process:session-1:run-a');
    expect(buildProcessRunIdempotencyKey('s', 'r')).toBe('mobile-process:s:r');
  });

  it('reuses the same run key for retries with the same mode', async () => {
    const a = await processingRunStore.getOrCreateForStart('session-1', 'CODE_SCAN');
    const b = await processingRunStore.getOrCreateForStart('session-1', 'CODE_SCAN');
    expect(a.id).toBe(b.id);
    expect(a.idempotencyKey).toBe(b.idempotencyKey);
  });

  it('creates a new run when identification mode changes', async () => {
    const a = await processingRunStore.getOrCreateForStart('session-1', 'CODE_SCAN');
    const b = await processingRunStore.getOrCreateForStart('session-1', 'INTERNAL_OCR');
    expect(a.id).not.toBe(b.id);
    expect(a.idempotencyKey).not.toBe(b.idempotencyKey);
  });

  it('readiness reports pending uploads', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploading', backend_asset_id: null },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('pending');
    const service = new ProcessingService(api as never, repo as never, jobs as never, uploadQueue as never, assetsApi as never, logger);
    const readiness = await service.readiness('session-1');
    expect(readiness.ready).toBe(false);
    expect(readiness.reason).toMatch(/pendientes/i);
  });

  it('startProcess reuses active backend job without duplicate POST', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('ready');
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      backend_job_id: 'job-1',
    });
    assetsApi.listAssets.mockResolvedValue([{ id: 'asset-1' }]);
    jobs.getByBackendJobId.mockResolvedValue({ status: 'running', backend_job_id: 'job-1' });
    const service = new ProcessingService(api as never, repo as never, jobs as never, uploadQueue as never, assetsApi as never, logger);
    const result = await service.startProcess('session-1');
    expect(result).toEqual({ ok: true, jobId: 'job-1', reason: null });
    expect(api.post).not.toHaveBeenCalled();
  });

  it('recovers existing job on 409 without creating another', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('ready');
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      backend_job_id: null,
    });
    assetsApi.listAssets.mockResolvedValue([{ id: 'asset-1' }]);
    jobs.getByBackendJobId.mockResolvedValue(null);
    api.get.mockResolvedValue({
      latest_job: { id: 'job-existing', status: 'running' },
      recent_jobs: [],
      operational_job_id: 'job-existing',
      aisle: {},
    });
    api.post.mockRejectedValue(new ApiError('active', 409, 'ACTIVE_JOB_EXISTS'));
    const service = new ProcessingService(api as never, repo as never, jobs as never, uploadQueue as never, assetsApi as never, logger);
    const result = await service.startProcess('session-1');
    expect(result.ok).toBe(true);
    expect(result.jobId).toBe('job-existing');
  });

  it('startProcess sends identification_mode with run-scoped key', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('ready');
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      backend_job_id: null,
    });
    assetsApi.listAssets.mockResolvedValue([{ id: 'asset-1' }]);
    jobs.getByBackendJobId.mockResolvedValue(null);
    api.get.mockResolvedValue({ latest_job: null, recent_jobs: [], operational_job_id: null, aisle: {} });
    api.post.mockResolvedValue({ job_id: 'job-new', identification_mode: 'CODE_SCAN' });
    const service = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      logger,
    );
    const result = await service.startProcess('session-1', { identificationMode: 'CODE_SCAN' });
    expect(result.ok).toBe(true);
    const body = api.post.mock.calls[0][1] as { idempotency_key: string; identification_mode: string };
    expect(body.identification_mode).toBe('CODE_SCAN');
    expect(body.idempotency_key).toMatch(/^mobile-process:session-1:/);
    expect(api.post.mock.calls[0][2]).toEqual({
      headers: { 'Idempotency-Key': body.idempotency_key },
    });
  });

  it('startProcess omits identification_mode when inheriting', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('ready');
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      backend_job_id: null,
    });
    assetsApi.listAssets.mockResolvedValue([{ id: 'asset-1' }]);
    jobs.getByBackendJobId.mockResolvedValue(null);
    api.get.mockResolvedValue({ latest_job: null, recent_jobs: [], operational_job_id: null, aisle: {} });
    api.post.mockResolvedValue({ job_id: 'job-new' });
    const service = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      logger,
    );
    await service.startProcess('session-1', { identificationMode: null });
    const body = api.post.mock.calls[0][1] as { idempotency_key: string; identification_mode?: string };
    expect(body.identification_mode).toBeUndefined();
    expect(body.idempotency_key).toMatch(/^mobile-process:session-1:/);
  });

  it('startProcess maps legacy-not-allowed to clear message', async () => {
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    uploadQueue.refreshSessionReadiness.mockResolvedValue('ready');
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      backend_job_id: null,
    });
    assetsApi.listAssets.mockResolvedValue([{ id: 'asset-1' }]);
    jobs.getByBackendJobId.mockResolvedValue(null);
    api.get.mockResolvedValue({ latest_job: null, recent_jobs: [], operational_job_id: null, aisle: {} });
    api.post.mockRejectedValue(
      new ApiError('blocked', 422, 'LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION'),
    );
    const service = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      logger,
    );
    const result = await service.startProcess('session-1', { identificationMode: 'INTERNAL_OCR' });
    expect(result.ok).toBe(false);
    expect(result.reason).toMatch(/ya no está disponible/i);
  });

  it('startProcess rejects concurrent double start with lock', async () => {
    let releaseReady!: (v: string) => void;
    const readyGate = new Promise<string>((resolve) => {
      releaseReady = resolve;
    });
    uploadQueue.refreshSessionReadiness.mockImplementation(() => readyGate);
    repo.listPhotos.mockResolvedValue([
      { status: 'stable', upload_status: 'uploaded', backend_asset_id: 'asset-1' },
    ]);
    const service = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      logger,
    );
    const first = service.startProcess('session-1', { identificationMode: 'CODE_SCAN' });
    // Allow first call to acquire the session lock and block on readiness.
    await new Promise((r) => setImmediate(r));
    const second = await service.startProcess('session-1', { identificationMode: 'INTERNAL_OCR' });
    expect(second).toEqual({ ok: false, jobId: null, reason: 'Procesamiento ya en curso.' });
    releaseReady('pending');
    const firstResult = await first;
    expect(firstResult.ok).toBe(false);
    expect(api.post).not.toHaveBeenCalled();
  }, 10000);

  it('getResultSummary does not invent zeros on merge error', async () => {
    repo.getSession.mockResolvedValue({
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-1',
      aisle_name: 'A1',
      processing_status: 'completed',
      backend_job_id: 'job-1',
      processing_finished_at: '2026-01-01T00:00:00Z',
      last_processing_error: null,
      updated_at: '2026-01-01T00:00:00Z',
    });
    repo.listPhotos.mockResolvedValue([{ upload_status: 'uploaded' }]);
    jobs.getLatestForSession.mockResolvedValue({
      backend_job_id: 'job-1',
      remote_status: 'completed',
      error_message: null,
      finished_at: '2026-01-01T00:00:00Z',
      last_polled_at: '2026-01-01T00:00:00Z',
    });
    api.get.mockRejectedValue(new ApiError('forbidden', 403, 'FORBIDDEN'));
    const service = new ProcessingService(
      api as never,
      repo as never,
      jobs as never,
      uploadQueue as never,
      assetsApi as never,
      logger,
    );
    const summary = await service.getResultSummary('session-1');
    expect(summary.loadState).toBe('error');
    expect(summary.positions).toBeNull();
    expect(summary.pendingReview).toBeNull();
  });
});
