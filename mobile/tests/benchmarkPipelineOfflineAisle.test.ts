import * as fs from 'fs';
import * as path from 'path';
import { createRequire } from 'module';

const requireCjs = createRequire(__filename);
const {
  collectOfflineAisleMetrics,
  assertOfflineAisleV2ZipLayout,
  assertOfflineAisleRun,
  OFFLINE_AISLE_SCHEMA_VERSION,
} = requireCjs('../scripts/lib/offlineAisleBenchmark.cjs') as {
  collectOfflineAisleMetrics: (events: unknown[]) => {
    payloadBytes: number | null;
    zipBytes: number | null;
    zipEntryCount: number | null;
    schemaVersion: number | null;
  };
  assertOfflineAisleV2ZipLayout: (entries: string[]) => string[];
  assertOfflineAisleRun: (input: {
    events: unknown[];
    status: Record<string, unknown>;
    zipEntries: string[];
    expectedCaptureCount?: number;
    validatorResult?: Record<string, unknown>;
  }) => { ok: boolean; failures: string[] };
  OFFLINE_AISLE_SCHEMA_VERSION: number;
};
const pipeline = requireCjs('../scripts/benchmark-pipeline.cjs') as {
  parseArgs: (argv: string[]) => { offlineAisle: boolean; photos: number; runs: number };
  validateSmokeInstrumentation: (
    events: unknown[],
    status: Record<string, unknown>,
    opts?: Record<string, unknown>,
  ) => { ok: boolean; failures: string[] };
};

describe('benchmark pipeline offline aisle coordinator', () => {
  test('parseArgs defaults preserve historical CSV-only behavior', () => {
    const args = pipeline.parseArgs(['--input', path.join('/tmp', 'andes-input-placeholder')]);
    expect(args.offlineAisle).toBe(false);
    expect(args.photos).toBe(3);
    expect(args.runs).toBe(1);
  });

  test('parseArgs enables --offline-aisle without changing worker default', () => {
    const args = pipeline.parseArgs([
      '--input',
      path.join('/tmp', 'andes-input-placeholder'),
      '--offline-aisle',
      '--photos',
      '3',
    ]);
    expect(args.offlineAisle).toBe(true);
    expect(args.photos).toBe(3);
  });

  test('smoke instrumentation ignores offline stages unless the flag is set', () => {
    const events = [
      { stage: 'zip_entry', extras: { entryKind: 'csv' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'manifest' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'photo' }, durationMs: 1, success: true },
      { stage: 'zip_finalize', durationMs: 10, success: true },
      { stage: 'total_export', durationMs: 40, success: true },
      { stage: 'zip_validation', durationMs: 5, success: true },
      { stage: 'staging_hash', extras: { hashMode: 'native_file' }, durationMs: 1, success: true },
      {
        stage: 'draft_lookup',
        extras: { lookupMode: 'direct_indexed_lookup', queryCount: 1, fullSessionRowsLoaded: 0 },
        durationMs: 1,
        success: true,
      },
      { stage: 'cleanup', durationMs: 1, success: true },
      { photoId: 'p1', fixtureId: 'f1', stage: 'photo_terminal', durationMs: 1, success: true },
    ];
    const status = { status: 'COMPLETED', terminalCount: 1, expectedCount: 1, pendingJobs: 0 };
    const withoutFlag = pipeline.validateSmokeInstrumentation(events, status);
    expect(withoutFlag.failures.some((f) => String(f).startsWith('offline_'))).toBe(false);
  });

  test('offline metrics and zip layout are required when flag is on', () => {
    const events = [
      {
        stage: 'offline_prepare',
        success: true,
        durationMs: 4,
      },
      {
        stage: 'offline_asset_prepare',
        success: true,
        durationMs: 4,
      },
      {
        stage: 'offline_payload_build',
        success: true,
        durationMs: 10,
        extras: { payloadBytes: 100 },
      },
      { stage: 'offline_integrity', success: true, durationMs: 4 },
      { stage: 'offline_validation', success: true, durationMs: 3, extras: { schemaVersion: 2 } },
      {
        stage: 'offline_zip',
        success: true,
        durationMs: 8,
        extras: { zipBytes: 500, zipEntryCount: 3 },
      },
      {
        stage: 'offline_total_export',
        success: true,
        durationMs: 30,
        extras: {
          payloadBytes: 100,
          zipBytes: 500,
          zipEntryCount: 3,
          captureCount: 3,
          assetCount: 3,
          schemaVersion: 2,
        },
      },
    ];
    const metrics = collectOfflineAisleMetrics(events);
    expect(metrics.payloadBytes).toBe(100);
    expect(metrics.zipBytes).toBe(500);
    expect(metrics.zipEntryCount).toBe(3);
    expect(metrics.schemaVersion).toBe(OFFLINE_AISLE_SCHEMA_VERSION);
    expect(
      assertOfflineAisleV2ZipLayout(['manifest.json', 'aisle-package.json', 'assets/a.jpg']),
    ).toEqual([]);
    expect(
      assertOfflineAisleRun({
        events,
        status: { status: 'COMPLETED' },
        zipEntries: ['manifest.json', 'aisle-package.json', 'assets/a.jpg'],
        expectedCaptureCount: 3,
        validatorResult: {
          valid: true,
          errors: [],
          manifest: { schema_version: 2, capture_count: 3 },
        },
      }).ok,
    ).toBe(true);
  });

  test('campaign fails when offline export or validation is missing', () => {
    const missing = assertOfflineAisleRun({
      events: [],
      status: { status: 'FAILED', errorCode: 'OFFLINE_AISLE_VALIDATION_FAILED' },
      zipEntries: [],
    });
    expect(missing.ok).toBe(false);
    expect(missing.failures.join(' ')).toMatch(/offline_total_export_count=0|status=FAILED/);
  });

  test('metrics zipEntryCount must match physical zip entry list when provided', () => {
    const events = [
      {
        stage: 'offline_prepare',
        success: true,
        durationMs: 1,
      },
      {
        stage: 'offline_asset_prepare',
        success: true,
        durationMs: 1,
      },
      {
        stage: 'offline_payload_build',
        success: true,
        durationMs: 1,
        extras: { payloadBytes: 10 },
      },
      { stage: 'offline_integrity', success: true, durationMs: 1 },
      { stage: 'offline_validation', success: true, durationMs: 1, extras: { schemaVersion: 2 } },
      {
        stage: 'offline_zip',
        success: true,
        durationMs: 1,
        extras: { zipBytes: 100, zipEntryCount: 99 },
      },
      {
        stage: 'offline_total_export',
        success: true,
        durationMs: 1,
        extras: {
          payloadBytes: 10,
          zipBytes: 100,
          zipEntryCount: 99,
          schemaVersion: 2,
        },
      },
    ];
    const mismatch = assertOfflineAisleRun({
      events,
      status: { status: 'COMPLETED' },
      zipEntries: ['manifest.json', 'aisle-package.json', 'assets/a.jpg'],
      validatorResult: {
        valid: true,
        errors: [],
        manifest: { schema_version: 2, capture_count: 1 },
      },
    });
    expect(mismatch.ok).toBe(false);
    expect(mismatch.failures.join(' ')).toContain('zipEntryCount_physical_mismatch');
  });

  test('validateSmokeInstrumentation reuses offline gate without validator_not_run', () => {
    const csvAndInstrumentation = [
      { stage: 'zip_entry', extras: { entryKind: 'csv' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'manifest' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'photo' }, durationMs: 1, success: true },
      { stage: 'zip_finalize', durationMs: 10, success: true },
      { stage: 'total_export', durationMs: 40, success: true },
      { stage: 'zip_validation', durationMs: 5, success: true },
      { stage: 'staging_hash', extras: { hashMode: 'native_file' }, durationMs: 1, success: true },
      {
        stage: 'draft_lookup',
        extras: { lookupMode: 'direct_indexed_lookup', queryCount: 1, fullSessionRowsLoaded: 0 },
        durationMs: 1,
        success: true,
      },
      { stage: 'cleanup', durationMs: 1, success: true, queueDepth: 0 },
      { photoId: 'p1', fixtureId: 'f1', stage: 'photo_terminal', durationMs: 1, success: true },
    ];
    const offlineStages = [
      { stage: 'offline_prepare', success: true, durationMs: 1 },
      { stage: 'offline_asset_prepare', success: true, durationMs: 1 },
      {
        stage: 'offline_payload_build',
        success: true,
        durationMs: 1,
        extras: { payloadBytes: 10 },
      },
      { stage: 'offline_integrity', success: true, durationMs: 1 },
      { stage: 'offline_validation', success: true, durationMs: 1, extras: { schemaVersion: 2 } },
      {
        stage: 'offline_zip',
        success: true,
        durationMs: 1,
        extras: { zipBytes: 100, zipEntryCount: 3 },
      },
      {
        stage: 'offline_total_export',
        success: true,
        durationMs: 1,
        extras: {
          payloadBytes: 10,
          zipBytes: 100,
          zipEntryCount: 3,
          captureCount: 1,
          schemaVersion: 2,
        },
      },
    ];
    const events = [...csvAndInstrumentation, ...offlineStages];
    const status = { status: 'COMPLETED', terminalCount: 1, expectedCount: 1, pendingJobs: 0 };
    const zipEntries = ['manifest.json', 'aisle-package.json', 'assets/a.jpg'];
    const offlineCheck = assertOfflineAisleRun({
      events,
      status,
      zipEntries,
      expectedCaptureCount: 1,
      validatorResult: {
        valid: true,
        errors: [],
        manifest: { schema_version: 2, capture_count: 1 },
      },
    });
    expect(offlineCheck.ok).toBe(true);

    const instr = pipeline.validateSmokeInstrumentation(events, status, {
      offlineAisle: true,
      offlineCheck,
    });
    expect(instr.failures.some((f) => f.includes('validator_not_run'))).toBe(false);
    expect(instr.failures.some((f) => f.startsWith('offline_'))).toBe(false);
    expect(instr.ok).toBe(true);
  });

  test('validateSmokeInstrumentation fails when offline gate reports backend validator errors', () => {
    const offlineCheck = {
      ok: false,
      failures: ['backend_validator_failed:bad_zip'],
    };
    const events = [
      { stage: 'zip_entry', extras: { entryKind: 'csv' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'manifest' }, durationMs: 1, success: true },
      { stage: 'zip_entry', extras: { entryKind: 'photo' }, durationMs: 1, success: true },
      { stage: 'zip_finalize', durationMs: 10, success: true },
      { stage: 'total_export', durationMs: 40, success: true },
      { stage: 'zip_validation', durationMs: 5, success: true },
      { stage: 'staging_hash', extras: { hashMode: 'native_file' }, durationMs: 1, success: true },
      {
        stage: 'draft_lookup',
        extras: { lookupMode: 'direct_indexed_lookup', queryCount: 1, fullSessionRowsLoaded: 0 },
        durationMs: 1,
        success: true,
      },
      { stage: 'cleanup', durationMs: 1, success: true, queueDepth: 0 },
      { photoId: 'p1', fixtureId: 'f1', stage: 'photo_terminal', durationMs: 1, success: true },
    ];
    const status = { status: 'COMPLETED', terminalCount: 1, expectedCount: 1, pendingJobs: 0 };
    const instr = pipeline.validateSmokeInstrumentation(events, status, {
      offlineAisle: true,
      offlineCheck,
    });
    expect(instr.ok).toBe(false);
    expect(instr.failures).toContain('offline_backend_validator_failed:bad_zip');
  });

  test('host offline aisle artifact uses physical zip entry count', () => {
    const src = fs.readFileSync(path.join(__dirname, '../scripts/benchmark-pipeline.cjs'), 'utf8');
    expect(src).toMatch(/zipEntryCount:\s*zipEntries\.length/);
    expect(src).not.toMatch(/zipEntryCount:\s*copied\.zipEntries\.length/);
  });

  test('physical package validator failure fails the host gate', () => {
    const failed = assertOfflineAisleRun({
      events: [],
      status: { status: 'COMPLETED' },
      zipEntries: [],
      expectedCaptureCount: 3,
      validatorResult: {
        valid: false,
        errors: ['bad_zip'],
        manifest: null,
      },
    });
    expect(failed.ok).toBe(false);
    expect(failed.failures.join(' ')).toContain('backend_validator_failed:bad_zip');
  });

  test('legacy zip paths fail validation', () => {
    expect(
      assertOfflineAisleV2ZipLayout(['manifest.json', 'aisle-package.json', 'aisle.json']),
    ).toEqual(['legacy_aisle.json']);
    expect(
      assertOfflineAisleV2ZipLayout([
        'manifest.json',
        'aisle-package.json',
        'recognition/profiles.json',
      ]),
    ).toEqual(['legacy_recognition/profiles.json']);
    expect(
      assertOfflineAisleV2ZipLayout([
        'manifest.json',
        'aisle-package.json',
        'captures/cap.json',
      ]),
    ).toEqual(['legacy_captures/cap.json']);
  });

  test('pipeline script still uses workers=2 and copies the package after status', () => {
    const src = fs.readFileSync(path.join(__dirname, '../scripts/benchmark-pipeline.cjs'), 'utf8');
    const lib = fs.readFileSync(
      path.join(__dirname, '../scripts/lib/offlineAisleBenchmark.cjs'),
      'utf8',
    );
    expect(src).toMatch(/PHASE4_EXPORT_PREP_MAX_WORKERS = 2/);
    expect(src).toMatch(/copyOfflineAislePackage/);
    expect(src).toMatch(/finalizeOfflineAisleArtifacts/);
    expect(lib).toMatch(/offline_total_export/);
    const pullAt = src.indexOf('copyOfflineAislePackage');
    const pollAt = src.indexOf('pollStatus(');
    expect(pollAt).toBeGreaterThan(0);
    expect(pullAt).toBeGreaterThan(0);
  });
});
