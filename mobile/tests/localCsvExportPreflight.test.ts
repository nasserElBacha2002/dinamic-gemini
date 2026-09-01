import { diagnoseExportBlockers } from '../src/features/localCsv/localCsvExportPreflight';
import {
  mapLocalCsvExportError,
  userMessageForLocalCsvExportError,
} from '../src/features/localCsv/runLocalCsvExport';

describe('diagnoseExportBlockers', () => {
  it('detects missing offline supplier profile', () => {
    const result = diagnoseExportBlockers(
      [{ id: 'p1', status: 'stable' } as never],
      [
        {
          capture_photo_id: 'p1',
          recognition_profile_snapshot_json: JSON.stringify({
            item_profile_missing: true,
          }),
        } as never,
      ],
    );
    expect(result?.code).toBe('PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED');
  });

  it('detects explicit aisle Supplier resolved as DINAMIC', () => {
    const result = diagnoseExportBlockers(
      [{ id: 'p1', status: 'stable' } as never],
      [
        {
          capture_photo_id: 'p1',
          recognition_profile_snapshot_json: JSON.stringify({
            client_supplier_id: null,
            item: { profile_source: 'DINAMIC', missing: false },
            position: { profile_source: 'DINAMIC', missing: false },
          }),
        } as never,
      ],
      {
        clientSupplierId: 'sup-b',
        itemSource: 'SUPPLIER',
        positionSource: 'SUPPLIER',
      },
    );
    expect(result?.code).toBe('OFFLINE_SUPPLIER_RECOGNITION_NOT_READY');
    const mapped = mapLocalCsvExportError(
      new Error(`${result?.code}: ${result?.detail}`),
    );
    expect(mapped.kind).toBe('offline_config');
  });

  it.each([
    ['SUPPLIER', 'SUPPLIER'],
    ['SUPPLIER', 'DINAMIC'],
    ['DINAMIC', 'SUPPLIER'],
    ['DINAMIC', 'DINAMIC'],
  ] as const)('accepts matching mixed sources ITEM=%s POSITION=%s', (itemSource, positionSource) => {
    const result = diagnoseExportBlockers(
      [{ id: 'p1', status: 'stable' } as never],
      [
        {
          capture_photo_id: 'p1',
          recognition_profile_snapshot_json: JSON.stringify({
            client_supplier_id: 'sup-b',
            item: { profile_source: itemSource, missing: false },
            position: { profile_source: positionSource, missing: false },
          }),
        } as never,
      ],
      { clientSupplierId: 'sup-b', itemSource, positionSource },
    );
    expect(result).toBeNull();
  });

  it('blocks a Supplier ID mismatch', () => {
    const result = diagnoseExportBlockers(
      [{ id: 'p1', status: 'stable' } as never],
      [
        {
          capture_photo_id: 'p1',
          recognition_profile_snapshot_json: JSON.stringify({
            client_supplier_id: 'sup-other',
            item: { profile_source: 'SUPPLIER' },
            position: { profile_source: 'DINAMIC' },
          }),
        } as never,
      ],
      { clientSupplierId: 'sup-b', itemSource: 'SUPPLIER', positionSource: 'DINAMIC' },
    );
    expect(result?.code).toBe('OFFLINE_SUPPLIER_RECOGNITION_NOT_READY');
  });
});

describe('mapLocalCsvExportError offline_config', () => {
  it('maps offline config required to user message', () => {
    const mapped = mapLocalCsvExportError(
      new Error('PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED: sin sync'),
    );
    expect(mapped.kind).toBe('offline_config');
    expect(userMessageForLocalCsvExportError(mapped)).toContain('configuración offline');
  });
});
