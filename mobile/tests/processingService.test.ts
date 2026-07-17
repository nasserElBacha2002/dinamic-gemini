import { processIdempotencyKey, ProcessingService } from '../src/features/processing/processingService';
import { createLogger } from '../src/core/logging';
import { ApiError } from '../src/services/api/apiClient';

describe('ProcessingService', () => {
  const api = { get: jest.fn(), post: jest.fn() };
  const repo = {
    listPhotos: jest.fn(),
    getSession: jest.fn(),
    updateSessionStatus: jest.fn(),
    updateSessionUploadMeta: jest.fn(),
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
  });

  it('uses stable idempotency key per session', () => {
    expect(processIdempotencyKey('session-1')).toBe('mobile-process:session-1');
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
    const service = new ProcessingService(api as never, repo as never, jobs as never, uploadQueue as never, assetsApi as never, logger);
    const summary = await service.getResultSummary('session-1');
    expect(summary.loadState).toBe('error');
    expect(summary.positions).toBeNull();
    expect(summary.pendingReview).toBeNull();
  });
});
