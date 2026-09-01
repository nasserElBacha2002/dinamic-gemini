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
