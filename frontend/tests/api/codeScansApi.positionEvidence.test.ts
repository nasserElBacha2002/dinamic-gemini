import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getPositionCodeScanEvidence } from '../../src/api/codeScansApi';

const apiRequestJson = vi.hoisted(() => vi.fn());

vi.mock('../../src/api/request', () => ({
  apiRequestJson,
}));

describe('getPositionCodeScanEvidence', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
  });

  it('calls position code-scan-evidence endpoint', async () => {
    apiRequestJson.mockResolvedValue({ latest_run: null, summary: {}, detections: [] });
    await getPositionCodeScanEvidence('inv-1', 'aisle-1', 'pos-1');
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining(
        '/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1/code-scan-evidence'
      )
    );
  });
});
