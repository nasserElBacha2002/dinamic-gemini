import { OfflineAisleExportService } from '../src/features/offlineAisleExport/offlineAisleExportService';
import type { OfflineAisleExportPhaseEvent } from '../src/features/offlineAisleExport/offlineAisleExportService';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { LocalDetectionDraftRow } from '../src/database/repositories/localDetectionDraftRepository';

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn(async () => true),
  shareAsync: jest.fn(async () => undefined),
}));

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  cacheDirectory: 'file:///cache/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  readAsStringAsync: jest.fn(async () => Buffer.from('jpeg-bytes').toString('base64')),
  writeAsStringAsync: jest.fn(async () => undefined),
  makeDirectoryAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
}));

function session(): CaptureSessionRow {
  const now = '2026-01-01T00:00:00.000Z';
  return {
    id: 'sess-1',
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_id: 'aisle-1',
    aisle_name: 'BENCH-TEST',
    status: 'local_completed',
    started_at: now,
    finished_at: now,
    capture_frozen_at: now,
    active_freeze_id: null,
    capture_freeze_generation: 1,
  } as unknown as CaptureSessionRow;
}

function photo(id: string): CapturePhotoRow {
  return {
    id,
    capture_session_id: 'sess-1',
    asset_id: `asset-${id}`,
    uri: `file:///${id}.jpg`,
    display_name: `${id}.jpg`,
    mime_type: 'image/jpeg',
    size: 12,
    width: 1,
    height: 1,
    status: 'stable',
    client_file_id: `cf-${id}`,
    sequence_number: 1,
    recognition_profile_snapshot_json: JSON.stringify({
      offline: true,
      client_supplier_id: 'sup-b',
      item: {
        status: 'VALID',
        profile_id: 'prof-item',
        profile_version: 10,
        profile_source: 'SUPPLIER',
        label_id: 'LPNA000184',
        sku: 'SKU773421',
        quantity: 24,
      },
    }),
  } as unknown as CapturePhotoRow;
}

function draft(): LocalDetectionDraftRow {
  return {
    id: 'd-item',
    capture_photo_id: 'cap-item',
    capture_session_id: 'sess-1',
    client_file_id: 'cf-cap-item',
    status: 'RESOLVED',
    internal_code: 'SKU773421',
    quantity: 24,
    error_code: null,
    label_id: 'LPNA000184',
    product_results_json: JSON.stringify([
      {
        labelId: 'LPNA000184',
        internalCode: 'SKU773421',
        quantity: 24,
        formatVersion: 'SUPPLIER',
        validationStatus: 'VALID',
        rawPayload: 'LPNA000184|SKU773421|24',
      },
    ]),
    recognition_profile_snapshot_json: JSON.stringify({
      offline: true,
      client_supplier_id: 'sup-b',
      item: {
        status: 'VALID',
        profile_id: 'prof-item',
        profile_version: 10,
        profile_source: 'SUPPLIER',
        label_id: 'LPNA000184',
        sku: 'SKU773421',
        quantity: 24,
      },
    }),
  } as unknown as LocalDetectionDraftRow;
}

function buildService(prepareSessionForExport = jest.fn(async () => undefined)) {
  const aisle = {
    id: 'aisle-1',
    inventory_id: 'inv-1',
    code: 'BENCH-TEST',
    client_supplier_id: 'sup-b',
    origin: 'LOCAL',
    sync_status: 'LOCAL_ONLY',
    created_offline_at: '2026-01-01T00:00:00.000Z',
  };
  const inventory = { id: 'inv-1', name: 'Inv', client_id: 'client-1' };
  return {
    prepareSessionForExport,
    service: new OfflineAisleExportService({
      catalogRepo: {
        getAisleById: jest.fn(async () => aisle),
        getInventoryById: jest.fn(async () => inventory),
        getSupplierById: jest.fn(async () => ({ name: 'andes' })),
      } as never,
      captureRepo: {
        listPhotos: jest.fn(async () => [photo('cap-item')]),
        listFreezePhotos: jest.fn(async () => [photo('cap-item')]),
      } as never,
      draftRepo: {
        listForSession: jest.fn(async () => [draft()]),
      } as never,
      listSessionsForAisle: jest.fn(async () => [session()]),
      sessionCsvExport: { prepareSessionForExport } as never,
      appVersion: 'test',
      enabled: true,
    }),
  };
}

describe('offline aisle export instrumentation', () => {
  test('onExportPhase is optional and production export still prepares the session', async () => {
    const { service, prepareSessionForExport } = buildService();
    const exported = await service.exportAisle({
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      includeAssets: false,
    });
    expect(prepareSessionForExport).toHaveBeenCalledTimes(1);
    expect(exported.schemaVersion).toBe(2);
    expect(exported.payloadBytes).toBeGreaterThan(0);
    expect(exported.zipBytes).toBeGreaterThan(0);
    expect(exported.zipEntryCount).toBeGreaterThanOrEqual(2);
    expect(exported.captureCount).toBe(1);
  });

  test('skipSessionPrepare does not call prepareSessionForExport', async () => {
    const { service, prepareSessionForExport } = buildService();
    await service.exportAisle({
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      includeAssets: false,
      skipSessionPrepare: true,
    });
    expect(prepareSessionForExport).not.toHaveBeenCalled();
  });

  test('emits nested offline phases once without shareExport', async () => {
    const Sharing = jest.requireMock('expo-sharing') as {
      shareAsync: jest.Mock;
      isAvailableAsync: jest.Mock;
    };
    const phases: OfflineAisleExportPhaseEvent[] = [];
    const { service } = buildService();
    await service.exportAisle({
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      includeAssets: false,
      skipSessionPrepare: true,
      onExportPhase: (event) => phases.push(event),
    });
    expect(phases.map((p) => p.phase)).toEqual([
      'offline_prepare',
      'offline_asset_prepare',
      'offline_payload_build',
      'offline_integrity',
      'offline_validation',
      'offline_zip',
      'offline_total_export',
    ]);
    expect(phases.every((p) => p.success)).toBe(true);
    const total = phases.find((p) => p.phase === 'offline_total_export');
    expect(total?.extras?.payloadBytes).toEqual(expect.any(Number));
    expect(total?.extras?.zipBytes).toEqual(expect.any(Number));
    expect(total?.extras?.zipEntryCount).toEqual(expect.any(Number));
    expect(total?.extras?.schemaVersion).toBe(2);
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
    expect(Sharing.isAvailableAsync).not.toHaveBeenCalled();
  });

  test('writes the package into outputDirectory when provided', async () => {
    const FileSystem = jest.requireMock('expo-file-system') as {
      moveAsync: jest.Mock;
    };
    FileSystem.moveAsync.mockClear();
    const { service } = buildService();
    const exported = await service.exportAisle({
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      includeAssets: false,
      skipSessionPrepare: true,
      outputDirectory: 'file:///docs/benchmark/run-1',
    });
    expect(exported.fileUri).toContain('file:///docs/benchmark/run-1/');
    expect(exported.fileUri).toMatch(/\.dinamic$/);
    expect(FileSystem.moveAsync).toHaveBeenCalledWith(
      expect.objectContaining({ to: exported.fileUri }),
    );
  });

  test('observer errors do not fail export', async () => {
    const { service } = buildService();
    await expect(
      service.exportAisle({
        inventoryId: 'inv-1',
        aisleId: 'aisle-1',
        includeAssets: false,
        skipSessionPrepare: true,
        onExportPhase: () => {
          throw new Error('observer boom');
        },
      }),
    ).resolves.toMatchObject({ captureCount: 1, schemaVersion: 2 });
  });
});
