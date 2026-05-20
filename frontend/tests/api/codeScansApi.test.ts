import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getAisleCodeScanSummary,
  listAisleCodeScans,
  runAisleCodeScan,
} from '../../src/api/codeScansApi';

const apiRequestJson = vi.fn();

vi.mock('../../src/api/request', () => ({
  apiRequestJson: (...args: unknown[]) => apiRequestJson(...args),
}));

describe('codeScansApi', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
  });

  it('runAisleCodeScan calls POST run endpoint', async () => {
    apiRequestJson.mockResolvedValue({ run: { id: 'run-1' } });
    await runAisleCodeScan('inv-1', 'aisle-1');
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining('/api/v3/inventories/inv-1/aisles/aisle-1/code-scans/run'),
      { method: 'POST' }
    );
  });

  it('runAisleCodeScan passes job_id query when provided', async () => {
    apiRequestJson.mockResolvedValue({ run: { id: 'run-1' } });
    await runAisleCodeScan('inv-1', 'aisle-1', { jobId: 'job-abc' });
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining('job_id=job-abc'),
      { method: 'POST' }
    );
  });

  it('listAisleCodeScans calls list endpoint', async () => {
    apiRequestJson.mockResolvedValue({ latest_run: null, detections: [] });
    await listAisleCodeScans('inv-1', 'aisle-1');
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v3\/inventories\/inv-1\/aisles\/aisle-1\/code-scans$/)
    );
  });

  it('getAisleCodeScanSummary calls summary endpoint', async () => {
    apiRequestJson.mockResolvedValue({ latest_run: null, items: [] });
    await getAisleCodeScanSummary('inv-1', 'aisle-1');
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining('/api/v3/inventories/inv-1/aisles/aisle-1/code-scans/summary')
    );
  });
});
