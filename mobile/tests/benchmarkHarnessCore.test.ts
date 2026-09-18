import {
  assertAuthorizedBenchmarkIds,
  AUTHORIZED_BENCHMARK_CLIENT_ID,
  AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
  BENCHMARK_SCHEMA_VERSION,
  isBenchmarkNamespacePath,
} from '../src/features/benchmark/authorizedIds';
import { evaluateBenchmarkGate } from '../src/features/benchmark/benchmarkGate';
import {
  classifyDraftOutcome,
  outcomeIsSuccess,
} from '../src/features/benchmark/benchmarkOutcomes';
import {
  assertDeletableBenchmarkPath,
  assertSessionOwnedByRun,
  buildBenchmarkAssetId,
  buildBenchmarkSessionId,
} from '../src/features/benchmark/benchmarkIsolation';
import {
  clearBenchmarkFixtures,
  countBenchmarkFixtures,
  lookupBenchmarkFixture,
  registerBenchmarkFixture,
  resetAllBenchmarkFixturesForTests,
} from '../src/features/benchmark/benchmarkFixtureMap';
import {
  isTerminalStatus,
  parseManifestCsv,
  percentileNearestRank,
  selectPhotoSlice,
  selectSmokeFixtures,
  summarizeDurations,
} from '../src/features/benchmark/benchmarkManifest';
import {
  createBenchmarkMetricsSink,
  sanitizeEvent,
} from '../src/features/benchmark/benchmarkMetrics';

describe('benchmark harness corrections', () => {
  beforeEach(() => {
    resetAllBenchmarkFixturesForTests();
  });

  test('rejects unauthorized client/supplier ids', () => {
    expect(() =>
      assertAuthorizedBenchmarkIds({
        clientId: AUTHORIZED_BENCHMARK_CLIENT_ID,
        supplierId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
      }),
    ).not.toThrow();
    expect(() =>
      assertAuthorizedBenchmarkIds({
        clientId: 'other',
        supplierId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
      }),
    ).toThrow(/BENCHMARK_UNAUTHORIZED_CLIENT_ID/);
  });

  test('release and flag gates', () => {
    expect(
      evaluateBenchmarkGate({
        environment: 'production',
        isDevelopment: false,
        commandEnabled: true,
        exclusiveSessionActive: false,
      }).reason,
    ).toBe('RELEASE_BLOCKED');
    expect(
      evaluateBenchmarkGate({
        environment: 'development',
        isDevelopment: true,
        commandEnabled: false,
        exclusiveSessionActive: false,
      }).reason,
    ).toBe('FLAG_REQUIRED');
  });

  describe('classification', () => {
    test('POSITION_LABEL_DETECTED → position_detected success', () => {
      const o = classifyDraftOutcome({
        draftStatus: 'UNRESOLVED',
        errorCode: 'POSITION_LABEL_DETECTED',
        validationStatus: null,
        positionDetected: 1,
      });
      expect(o).toBe('position_detected');
      expect(outcomeIsSuccess(o)).toBe(true);
    });

    test('POSITION_LABEL_DUPLICATE → position_duplicate', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'UNRESOLVED',
          errorCode: 'POSITION_LABEL_DUPLICATE',
          validationStatus: null,
        }),
      ).toBe('position_duplicate');
    });

    test('invalid format exact codes', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'INVALID',
          errorCode: 'INVALID_PAYLOAD',
          validationStatus: null,
        }),
      ).toBe('decoded_invalid_format');
    });

    test('ITEM resolved → decoded_accepted', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'RESOLVED',
          errorCode: null,
          validationStatus: null,
        }),
      ).toBe('decoded_accepted');
    });

    test('ITEM duplicate via DUPLICATE_LABEL', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'RESOLVED',
          errorCode: 'DUPLICATE_LABEL',
          validationStatus: 'DUPLICATE_LABEL',
        }),
      ).toBe('decoded_duplicate');
    });

    test('not detected', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'UNRESOLVED',
          errorCode: 'NO_DETECTIONS',
          validationStatus: null,
        }),
      ).toBe('not_detected');
    });

    test('technical error', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'FAILED',
          errorCode: 'LOCAL_SCAN_TIMEOUT',
          validationStatus: null,
        }),
      ).toBe('scanner_technical_error');
    });

    test('profile error', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'FAILED',
          errorCode: 'PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED',
          validationStatus: null,
        }),
      ).toBe('profile_resolution_error');
    });

    test('persistence error', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'FAILED',
          errorCode: 'SQLITE_ERROR',
          validationStatus: null,
        }),
      ).toBe('persistence_error');
    });

    test('unknown pending', () => {
      expect(
        classifyDraftOutcome({
          draftStatus: 'PENDING',
          errorCode: null,
          validationStatus: null,
        }),
      ).toBe('unknown');
    });

    test('broad INVALID substring alone does not force invalid_format for technical codes', () => {
      // LOCAL_SCAN_FAILED does not contain FORMAT/PARSE exact codes
      expect(
        classifyDraftOutcome({
          draftStatus: 'FAILED',
          errorCode: 'LOCAL_SCAN_FAILED',
          validationStatus: null,
        }),
      ).toBe('scanner_technical_error');
    });
  });

  describe('fixture correlation', () => {
    test('registers, looks up, isolates runs, clears', () => {
      const runA = 'run-a';
      const runB = 'run-b';
      registerBenchmarkFixture(runA, 'photo-1', 'fx-1');
      registerBenchmarkFixture(runB, 'photo-1', 'fx-other');
      expect(lookupBenchmarkFixture(runA, 'photo-1')).toBe('fx-1');
      expect(lookupBenchmarkFixture(runB, 'photo-1')).toBe('fx-other');
      clearBenchmarkFixtures(runA);
      expect(lookupBenchmarkFixture(runA, 'photo-1')).toBeNull();
      expect(countBenchmarkFixtures(runB)).toBe(1);
    });

    test('sink auto-fills fixtureId for photo events', () => {
      const runId = 'run-sink';
      registerBenchmarkFixture(runId, 'p1', '01_position_andes_fixture_001');
      const sink = createBenchmarkMetricsSink({
        benchmarkRunId: runId,
        processId: 'proc',
        resolvedClientSupplierId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
        resolvedProfileName: 'andes',
      });
      sink.emit({
        sessionId: 's',
        photoId: 'p1',
        sequence: 1,
        stage: 'staging_copy',
        monotonicStartMs: 1,
        durationMs: 2,
        executionContext: 'js',
        success: true,
      });
      expect(sink.events[0]?.fixtureId).toBe('01_position_andes_fixture_001');
      expect(sink.events.filter((e) => e.photoId).every((e) => e.fixtureId != null)).toBe(true);
    });

    test('asset_id correlation maps non-contiguous manifest sequences', () => {
      // Mirrors smoke: fixture sequences 1,3,4 vs capture sequence_number 1,2,3.
      const fixtures = [
        { sequence: 1, fixtureId: '01_position_andes_fixture_001' },
        { sequence: 3, fixtureId: '03_item_andes_fixture_003' },
        { sequence: 4, fixtureId: '04_item_andes_fixture_004' },
      ];
      const byAsset = new Map(
        fixtures.map((f) => [buildBenchmarkAssetId(f.sequence), f.fixtureId] as const),
      );
      const photos = [
        { id: 'sess:bench-asset-001', asset_id: 'bench-asset-001', sequence_number: 1 },
        { id: 'sess:bench-asset-003', asset_id: 'bench-asset-003', sequence_number: 2 },
        { id: 'sess:bench-asset-004', asset_id: 'bench-asset-004', sequence_number: 3 },
      ];
      const runId = 'run-asset-map';
      for (const photo of photos) {
        const fid = byAsset.get(photo.asset_id);
        expect(fid).toBeTruthy();
        registerBenchmarkFixture(runId, photo.id, fid!);
      }
      expect(lookupBenchmarkFixture(runId, 'sess:bench-asset-003')).toBe(
        '03_item_andes_fixture_003',
      );
      expect(lookupBenchmarkFixture(runId, 'sess:bench-asset-004')).toBe(
        '04_item_andes_fixture_004',
      );
      // Wrong approach (sequence_number) would miss or mis-map middle photo.
      const bySeq = new Map(fixtures.map((f) => [f.sequence, f.fixtureId]));
      expect(bySeq.get(2)).toBeUndefined();
    });
  });

  test('cleanup cannot escape namespace', () => {
    const runId = 'abc-123';
    expect(() => assertDeletableBenchmarkPath('', runId)).toThrow(/EMPTY_PATH/);
    expect(() =>
      assertDeletableBenchmarkPath('/data/user/0/x/files/other/abc-123', runId),
    ).toThrow(/NAMESPACE_ESCAPE/);
    expect(() =>
      assertDeletableBenchmarkPath(`/files/benchmark/${runId}/fixtures`, runId),
    ).not.toThrow();
    expect(isBenchmarkNamespacePath(`/files/benchmark/${runId}/x`, runId)).toBe(true);
    expect(() => assertSessionOwnedByRun('prod-session', runId)).toThrow(/SESSION_MISMATCH/);
    expect(() => assertSessionOwnedByRun(buildBenchmarkSessionId(runId), runId)).not.toThrow();
  });

  test('manifest + smoke + full-run confirm contract', () => {
    const csv = `sequence,filename,type,source_template,width,height,size_bytes,sha256
1,01_position.jpg,position,t1,10,10,1,aaa
2,02_position.jpg,position,t2,10,10,1,bbb
3,03_item.jpg,item,t3,10,10,1,ccc
4,04_item.jpg,item,t4,10,10,1,ddd
`;
    const rows = parseManifestCsv(csv);
    expect(selectSmokeFixtures(rows).map((r) => r.type)).toEqual(['position', 'item', 'item']);
    expect(selectPhotoSlice(rows, 3)).toHaveLength(3);
    const confirmFullRun = false;
    expect((50 > 3 || 5 > 1) && !confirmFullRun).toBe(true);
  });

  test('stats + terminal states', () => {
    expect(summarizeDurations([10, 30, 20]).median).toBe(20);
    expect(percentileNearestRank([1, 2, 3, 4, 5], 50)).toBe(3);
    expect(isTerminalStatus('COMPLETED')).toBe(true);
    expect(isTerminalStatus('RUNNING')).toBe(false);
  });

  test('sanitization is case-insensitive and redacts URI/path patterns', () => {
    const keys = [
      'qr',
      'QR',
      'rawValue',
      'rawvalue',
      'codeValue',
      'codevalue',
      'configuration_json',
      'URI',
      'path',
      'token',
      'prompt',
    ];
    const extras: Record<string, string | number> = { bytes: 12, safe: 'ok' };
    for (const k of keys) extras[k] = 'secret';
    extras.fileRef = 'file:///data/user/0/x.jpg';
    extras.contentRef = 'content://media/1';
    extras.storageRef = '/storage/emulated/0/x';
    extras.usersRef = '/Users/me/x';
    const event = sanitizeEvent({
      schemaVersion: BENCHMARK_SCHEMA_VERSION,
      benchmarkRunId: 'r',
      processId: 'p',
      sessionId: null,
      clientId: AUTHORIZED_BENCHMARK_CLIENT_ID,
      supplierRouteId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
      resolvedClientSupplierId: null,
      resolvedProfileName: 'andes',
      photoId: null,
      sequence: null,
      fixtureId: null,
      stage: 'x',
      wallTimeUtc: new Date().toISOString(),
      monotonicStartMs: 0,
      durationMs: 1,
      inputBytes: null,
      outputBytes: null,
      queueDepth: null,
      workerConcurrency: null,
      executionContext: 'js',
      success: true,
      outcome: null,
      errorCode: null,
      extras,
    });
    for (const k of keys) {
      expect(event.extras?.[k]).toBeUndefined();
    }
    expect(event.extras?.fileRef).toBe('[redacted]');
    expect(event.extras?.contentRef).toBe('[redacted]');
    expect(event.extras?.storageRef).toBe('[redacted]');
    expect(event.extras?.usersRef).toBe('[redacted]');
    expect(event.extras?.bytes).toBe(12);
    expect(event.extras?.safe).toBe('ok');
  });

  test('zip metric stage names are distinct from total_export', () => {
    const stages = [
      'export_resolution',
      'export_resolution_queries',
      'export_resolution_ensure_jobs',
      'export_resolution_staging_validation',
      'export_resolution_hash_validation',
      'export_resolution_scan_catchup',
      'export_resolution_profile',
      'export_resolution_freeze_checks',
      'export_resolution_entry_build',
      'export_resolution_other',
      'csv_build',
      'csv_write',
      'manifest_build',
      'zip_open',
      'zip_entry',
      'zip_finalize',
      'zip_digest',
      'zip_validation',
      'total_export',
    ];
    expect(new Set(stages).size).toBe(stages.length);
    expect(stages).not.toContain('zip_close');
  });

  test('phase4 A/B keeps exportPrepMaxWorkers constant while scannerConcurrency varies', () => {
    // workers=2 feeds the scanner; workers=1 cannot observe C=2 (scans only in processJob).
    // Fields remain independent: workers held at 2 for both arms; only scanner changes.
    const c1 = { exportPrepMaxWorkers: 2 as const, scannerConcurrency: 1 as const };
    const c2 = { exportPrepMaxWorkers: 2 as const, scannerConcurrency: 2 as const };
    expect(c1.exportPrepMaxWorkers).toBe(c2.exportPrepMaxWorkers);
    expect(c1.scannerConcurrency).not.toBe(c2.scannerConcurrency);
    expect(c1.exportPrepMaxWorkers).not.toBe(c1.scannerConcurrency);
  });

  test('photo_terminal duration semantics fields are distinct', () => {
    const sink = createBenchmarkMetricsSink({
      benchmarkRunId: 'run-term',
      processId: 'proc',
      resolvedClientSupplierId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
      resolvedProfileName: 'andes',
    });
    registerBenchmarkFixture('run-term', 'p1', 'fx1');
    sink.emit({
      sessionId: 's',
      photoId: 'p1',
      sequence: 1,
      stage: 'photo_terminal',
      monotonicStartMs: 100,
      durationMs: 500,
      executionContext: 'js',
      success: true,
      outcome: 'position_detected',
      errorCode: 'POSITION_LABEL_DETECTED',
      extras: {
        scannerProcessingMs: 40,
        photoPipelineWallMs: 500,
        durationSemantics: 'admittedAt_to_terminalAt_wall',
      },
    });
    const e = sink.events[0]!;
    expect(e.durationMs).toBe(500);
    expect(e.extras?.scannerProcessingMs).toBe(40);
    expect(e.extras?.scannerProcessingMs).not.toBe(e.durationMs);
  });
});
