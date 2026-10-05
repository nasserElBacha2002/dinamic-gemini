import * as fs from 'fs';
import * as path from 'path';

const root = path.join(__dirname, '..');

function read(rel: string): string {
  return fs.readFileSync(path.join(root, rel), 'utf8');
}

describe('benchmark offline aisle source contracts', () => {
  test('offline export is invoked after exportSession and before purge/cleanup', () => {
    const runner = read('src/features/benchmark/benchmarkRunner.ts');
    const exportSessionAt = runner.indexOf('exportSession: () =>');
    const offlineAt = runner.indexOf('exportOfflineAisle: () =>');
    const purgeAt = runner.indexOf('sessionPurge.purgeSession');
    const cancelAt = runner.indexOf("updateSessionStatus(registry.sessionId, 'cancelled')");
    const deactivateAt = runner.indexOf('deactivateLocalAisle');
    const fixturesAt = runner.lastIndexOf('deleteAsync(fixturesDir');
    expect(exportSessionAt).toBeGreaterThan(0);
    expect(offlineAt).toBeGreaterThan(exportSessionAt);
    expect(purgeAt).toBeGreaterThan(offlineAt);
    expect(cancelAt).toBeGreaterThan(offlineAt);
    expect(deactivateAt).toBeGreaterThan(offlineAt);
    expect(fixturesAt).toBeGreaterThan(offlineAt);
    expect(runner).toMatch(/command\.offlineAisle === true/);
    expect(runner).not.toMatch(/shareExport\(/);
  });

  test('command watch injects the existing offlineAisleExport service', () => {
    const watch = read('src/features/benchmark/benchmarkCommandWatch.ts');
    expect(watch).toMatch(/offlineAisleExport:\s*services\.offlineAisleExport/);
    expect(watch).toMatch(/isDevelopment/);
    expect(watch).toMatch(/environment !== 'production'/);
  });

  test('cleanup remains scoped to the benchmark namespace', () => {
    const runner = read('src/features/benchmark/benchmarkRunner.ts');
    expect(runner).toMatch(/assertDeletableBenchmarkPath\(sandboxRoot, runId\)/);
    expect(runner).toMatch(/assertDeletableBenchmarkPath\(fixturesDir, runId\)/);
    expect(runner).not.toMatch(/MediaStore/);
    expect(runner).not.toMatch(/DCIM/);
  });

  test('helper skips session prepare and never shares', () => {
    const helper = read('src/features/benchmark/benchmarkOfflineAisle.ts');
    expect(helper).toMatch(/skipSessionPrepare:\s*true/);
    expect(helper).toMatch(/includeAssets:\s*true/);
    expect(helper).toMatch(/requireAssets:\s*true/);
    expect(helper).not.toMatch(/shareExport/);
    expect(helper).not.toMatch(/enqueueStablePhoto/);
    expect(helper).not.toMatch(/prepareSessionForExport/);
  });
});
