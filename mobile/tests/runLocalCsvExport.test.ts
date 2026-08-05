import { runLocalCsvExport } from '../src/features/localCsv/runLocalCsvExport';
import type { ExportedLocalCsv, LocalCsvExportService } from '../src/features/localCsv/localCsvExportService';

describe('runLocalCsvExport', () => {
  const exported: ExportedLocalCsv = {
    exportId: 'exp-1',
    fileUri: 'file://x.csv',
    zipUri: 'file://x.zip',
    checksumSha256: 'abc',
    rowCount: 2,
    photoCount: 2,
    packageChecksumSha256: 'pkg',
    reused: false,
  };

  it('returns shared=false when share is disabled', async () => {
    const service = {
      exportSession: jest.fn().mockResolvedValue(exported),
      shareExport: jest.fn(),
    } as unknown as LocalCsvExportService;
    const result = await runLocalCsvExport(service, 'session-1', { share: false });
    expect(result.exported).toEqual(exported);
    expect(result.shared).toBe(false);
    expect(service.shareExport).not.toHaveBeenCalled();
  });

  it('treats share cancel as non-fatal and keeps export result', async () => {
    const service = {
      exportSession: jest.fn().mockResolvedValue(exported),
      shareExport: jest.fn().mockRejectedValue(new Error('User did not share the file')),
    } as unknown as LocalCsvExportService;
    const result = await runLocalCsvExport(service, 'session-1');
    expect(result.exported.exportId).toBe('exp-1');
    expect(result.shared).toBe(false);
  });

  it('re-export can reuse prior package without throwing', async () => {
    const reused: ExportedLocalCsv = { ...exported, reused: true };
    const service = {
      exportSession: jest.fn().mockResolvedValue(reused),
      shareExport: jest.fn().mockResolvedValue(undefined),
    } as unknown as LocalCsvExportService;
    const first = await runLocalCsvExport(service, 'session-1');
    const second = await runLocalCsvExport(service, 'session-1');
    expect(first.exported.reused).toBe(true);
    expect(second.exported.reused).toBe(true);
    expect(service.exportSession).toHaveBeenCalledTimes(2);
  });
});
