import { nextSequenceAssignments } from '../src/core/captureSequence';
import { AisleAssetsApi } from '../src/features/upload/aisleAssetsApi';
import { OrderedCaptureApi } from '../src/features/upload/orderedCaptureApi';
import { MIGRATIONS } from '../src/database/migrations/migrations';

describe('captureSequence', () => {
  it('assigns monotonic 1..N in gallery order for photos missing sequence', () => {
    const assignments = nextSequenceAssignments([
      { id: 'a', sequence_number: null },
      { id: 'b', sequence_number: null },
      { id: 'c', sequence_number: null },
    ]);
    expect(assignments).toEqual([
      { id: 'a', sequenceNumber: 1 },
      { id: 'b', sequenceNumber: 2 },
      { id: 'c', sequenceNumber: 3 },
    ]);
  });

  it('survives reopen: never recalculates existing sequence_number values', () => {
    const first = nextSequenceAssignments([
      { id: 'a', sequence_number: null },
      { id: 'b', sequence_number: null },
    ]);
    expect(first).toEqual([
      { id: 'a', sequenceNumber: 1 },
      { id: 'b', sequenceNumber: 2 },
    ]);

    // Reopen / retry with a late photo: keep 1 and 2, assign 3 to the new row only.
    const second = nextSequenceAssignments([
      { id: 'a', sequence_number: 1 },
      { id: 'late', sequence_number: null },
      { id: 'b', sequence_number: 2 },
    ]);
    expect(second).toEqual([{ id: 'late', sequenceNumber: 3 }]);
  });

  it('continues from max existing even when gaps exist', () => {
    const assignments = nextSequenceAssignments([
      { id: 'a', sequence_number: 1 },
      { id: 'b', sequence_number: 5 },
      { id: 'c', sequence_number: null },
    ]);
    expect(assignments).toEqual([{ id: 'c', sequenceNumber: 6 }]);
  });
});

describe('AisleAssetsApi.uploadBatch ordered capture fields', () => {
  it('appends ordered_capture_session_id and sequence_numbers to FormData', async () => {
    const appended: { key: string; value: unknown }[] = [];
    const formStub = {
      append(key: string, value: unknown) {
        appended.push({ key, value });
      },
    };
    const g = globalThis as { FormData?: new () => unknown };
    const OriginalFormData = g.FormData;
    g.FormData = function FormDataStub() {
      return formStub;
    } as unknown as new () => unknown;

    const postMultipart = jest.fn(async () => ({
      assets: [],
      batch_id: 'batch-1',
      uploaded: [],
      errors: [],
    }));
    const api = { postMultipart } as never;
    const assetsApi = new AisleAssetsApi(api);

    try {
      await assetsApi.uploadBatch({
        inventoryId: 'inv-1',
        aisleId: 'aisle-1',
        uploadBatchId: 'batch-1',
        clientFileIds: ['cf-a', 'cf-b'],
        sequenceNumbers: [1, 2],
        orderedCaptureSessionId: 'ocs-1',
        files: [
          { uri: 'file://a.jpg', name: 'a.jpg', mimeType: 'image/jpeg' },
          { uri: 'file://b.jpg', name: 'b.jpg', mimeType: 'image/jpeg' },
        ],
      });
    } finally {
      if (OriginalFormData) {
        g.FormData = OriginalFormData;
      } else {
        delete g.FormData;
      }
    }

    expect(appended.filter((e) => e.key === 'client_file_ids').map((e) => e.value)).toEqual([
      'cf-a',
      'cf-b',
    ]);
    expect(appended.filter((e) => e.key === 'sequence_numbers').map((e) => e.value)).toEqual([
      '1',
      '2',
    ]);
    expect(
      appended.find((e) => e.key === 'ordered_capture_session_id')?.value,
    ).toBe('ocs-1');
    expect(postMultipart).toHaveBeenCalledWith(
      '/api/v3/inventories/inv-1/aisles/aisle-1/assets',
      formStub,
      expect.objectContaining({ timeoutMs: 120_000 }),
    );
  });
});

describe('OrderedCaptureApi', () => {
  it('posts create and seal to the inventories-mounted paths', async () => {
    const post = jest.fn(async (_path: string) => ({
      id: 'ocs-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      status: 'open',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }));
    const api = new OrderedCaptureApi({ post } as never);
    await api.createSession('inv-1', 'aisle-1');
    expect(post).toHaveBeenCalledWith(
      '/api/v3/inventories/inv-1/aisles/aisle-1/ordered-capture-sessions',
      {},
    );
    await api.sealSession('ocs-1', { expected_asset_count: 3, sequence_version: 1 });
    expect(post).toHaveBeenCalledWith(
      '/api/v3/inventories/ordered-capture-sessions/ocs-1/seal',
      { expected_asset_count: 3, sequence_version: 1 },
    );
  });
});

describe('migration v20', () => {
  it('is present after v19', () => {
    expect(MIGRATIONS[MIGRATIONS.length - 1]?.version).toBe(23);
  });
});
