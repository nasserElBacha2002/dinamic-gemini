/**
 * Phase 2 closure — draft_lookup timer isolation and pre/post purpose stages.
 */

import { ExportPrepQueue } from '../src/features/exportPrep/exportPrepQueue';
import {
  canonicalizeDraftsByPhoto,
  selectCanonicalDraftForSessionPhoto,
} from '../src/database/repositories/localDetectionDraftRepository';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 12 })),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(async () => 'c'.repeat(64)),
  hashStagedFileSha256Detailed: jest.fn(async () => ({
    sha256: 'c'.repeat(64),
    bytesHashed: 12,
    hashMode: 'native_file' as const,
    hashSource: 'computed' as const,
    durationMs: 1,
  })),
  classifyStagedDigestError: jest.fn(() => ({ failure: 'STAGING_DIGEST_FAILED' })),
}));

jest.mock('../src/features/exportPrep/digestAbsoluteFile', () => ({
  assertNativeDigestCapability: jest.fn(),
}));

jest.mock('../src/features/exportPrep/exportStaging', () => ({
  stageOriginalPhotoVersioned: jest.fn(async () => ({
    stagingUri: 'file:///docs/export-staging/s1/0001_p1.jpg',
    sizeBytes: 12,
  })),
  deleteSessionExportStaging: jest.fn(async () => undefined),
}));

describe('phase2 draft_lookup instrumentation', () => {
  test('selectCanonicalDraftForSessionPhoto prefers generation then updated_at', () => {
    const rows = [
      {
        id: 'a',
        scan_generation: 1,
        updated_at: '2026-01-03T00:00:00.000Z',
        created_at: '2026-01-01T00:00:00.000Z',
      },
      {
        id: 'b',
        scan_generation: 2,
        updated_at: '2026-01-01T00:00:00.000Z',
        created_at: '2026-01-02T00:00:00.000Z',
      },
    ] as never;
    expect((selectCanonicalDraftForSessionPhoto(rows) as { id: string } | null)?.id).toBe('b');
  });

  test('canonical selection is independent of input order (multi-draft)', () => {
    const olderUnresolved = {
      id: 'old',
      capture_photo_id: 'p1',
      scan_generation: 1,
      updated_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
      status: 'UNRESOLVED',
      prepared_asset_fingerprint: 'fp-a',
    };
    const newerResolved = {
      id: 'new',
      capture_photo_id: 'p1',
      scan_generation: 3,
      updated_at: '2026-01-02T00:00:00.000Z',
      created_at: '2026-01-02T00:00:00.000Z',
      status: 'RESOLVED',
      prepared_asset_fingerprint: 'fp-b',
    };
    const mid = {
      id: 'mid',
      capture_photo_id: 'p1',
      scan_generation: 2,
      updated_at: '2026-01-04T00:00:00.000Z',
      created_at: '2026-01-03T00:00:00.000Z',
      status: 'SCANNING',
      prepared_asset_fingerprint: 'fp-c',
    };
    const forward = [olderUnresolved, mid, newerResolved];
    const reverse = [newerResolved, mid, olderUnresolved];
    expect((selectCanonicalDraftForSessionPhoto(forward) as { id: string } | null)?.id).toBe('new');
    expect((selectCanonicalDraftForSessionPhoto(reverse) as { id: string } | null)?.id).toBe('new');
    expect((canonicalizeDraftsByPhoto(forward).get('p1') as { id: string } | undefined)?.id).toBe(
      'new',
    );
    expect((canonicalizeDraftsByPhoto(reverse).get('p1') as { id: string } | undefined)?.id).toBe(
      'new',
    );
  });

  test('updated_at breaks ties when scan_generation equal; created_at last', () => {
    const a = {
      id: 'a',
      capture_photo_id: 'p1',
      scan_generation: 2,
      updated_at: '2026-01-02T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
    };
    const b = {
      id: 'b',
      capture_photo_id: 'p1',
      scan_generation: 2,
      updated_at: '2026-01-03T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
    };
    const c = {
      id: 'c',
      capture_photo_id: 'p1',
      scan_generation: 2,
      updated_at: '2026-01-03T00:00:00.000Z',
      created_at: '2026-01-04T00:00:00.000Z',
    };
    expect((selectCanonicalDraftForSessionPhoto([a, b]) as { id: string } | null)?.id).toBe('b');
    expect((selectCanonicalDraftForSessionPhoto([b, a]) as { id: string } | null)?.id).toBe('b');
    expect((selectCanonicalDraftForSessionPhoto([b, c]) as { id: string } | null)?.id).toBe('c');
    expect((selectCanonicalDraftForSessionPhoto([c, b]) as { id: string } | null)?.id).toBe('c');
  });

  test('status does not override scan_generation / timestamps', () => {
    const unresolvedNewer = {
      id: 'u',
      capture_photo_id: 'p1',
      scan_generation: 5,
      updated_at: '2026-01-05T00:00:00.000Z',
      created_at: '2026-01-05T00:00:00.000Z',
      status: 'UNRESOLVED',
    };
    const resolvedOlder = {
      id: 'r',
      capture_photo_id: 'p1',
      scan_generation: 1,
      updated_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
      status: 'RESOLVED',
    };
    expect(
      (selectCanonicalDraftForSessionPhoto([resolvedOlder, unresolvedNewer]) as { id: string } | null)
        ?.id,
    ).toBe('u');
    expect(
      (selectCanonicalDraftForSessionPhoto([unresolvedNewer, resolvedOlder]) as { id: string } | null)
        ?.id,
    ).toBe('u');
  });

  test('DRAFT_DUPLICATE_INVARIANT is not part of DraftLookupError codes', () => {
    // Multi-draft case B: multiples are valid; no dead invariant enum.
    const { DraftLookupError } = jest.requireActual(
      '../src/database/repositories/localDetectionDraftRepository',
    ) as typeof import('../src/database/repositories/localDetectionDraftRepository');
    const err = new DraftLookupError('DRAFT_LOOKUP_FAILED', 'x');
    expect(err.code).toBe('DRAFT_LOOKUP_FAILED');
    expect(err.code).not.toBe('DRAFT_DUPLICATE_INVARIANT' as never);
  });

  test('draft_lookup duration excludes countsForSession; pre and post are distinct', async () => {
    const stages: Array<{
      stage: string;
      durationMs: number;
      extras?: Record<string, unknown>;
    }> = [];

    let lookupCalls = 0;
    const getBySessionAndPhotoId = jest.fn(async () => {
      lookupCalls += 1;
      await new Promise((r) => setTimeout(r, 5));
      return {
        draft: {
          id: 'd1',
          capture_photo_id: 'p1',
          capture_session_id: 's1',
          status: 'RESOLVED',
          internal_code: 'SKU',
          label_id: 'L1',
          product_results_json: '[]',
          position_detected: 0,
          parser_version: 'p',
          detector_version: 'd',
          prepared_asset_fingerprint: 'fp',
          scan_generation: 1,
          created_at: '2026-01-01T00:00:00.000Z',
          updated_at: '2026-01-01T00:00:00.000Z',
        },
        rowsMatched: 1,
        lookupMode: 'direct_indexed_lookup' as const,
        queryCount: 1 as const,
        fullSessionRowsLoaded: 0 as const,
        selectionRule: 'scan_generation_desc_updated_at_desc_created_at_desc' as const,
      };
    });

    let countsCalls = 0;
    const countsForSession = jest.fn(async () => {
      countsCalls += 1;
      await new Promise((r) => setTimeout(r, 40));
      return {
        queued: 0,
        preparing: 0,
        scanning: 0,
        validating: 0,
        ready: 1,
        failedRetryable: 0,
        failedTerminal: 0,
        excluded: 0,
        pending: 0,
        processing: 0,
        failed: 0,
        total: 1,
      };
    });

    const job = {
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      status: 'PREPARING' as const,
      source_uri: 'file://source/a.jpg',
      staging_uri: null,
      export_file_name: '0001_p1.jpg',
      size_bytes: null,
      sha256: null,
      source_fingerprint: null,
      error_code: null,
      error_message: null,
      attempt_count: 1,
      max_attempts: 3,
      lease_token: 'lease-1',
      lease_expires_at: '2099-01-01T00:00:00.000Z',
      queued_at: '2026-01-01T00:00:00.000Z',
      started_at: '2026-01-01T00:00:00.000Z',
      ready_at: null,
      updated_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
    };

    const queue = new ExportPrepQueue({
      prepRepo: {
        renewLease: jest.fn(async () => undefined),
        markScanning: jest.fn(async () => undefined),
        markValidating: jest.fn(async () => undefined),
        markReady: jest.fn(async () => undefined),
        markFailedFenced: jest.fn(async () => 'FAILED_RETRYABLE' as const),
        markExcluded: jest.fn(async () => undefined),
        countsForSession,
      } as never,
      captureRepo: {
        getPhotoById: async () => ({
          id: 'p1',
          capture_session_id: 's1',
          status: 'stable',
          uri: 'file://source/a.jpg',
          sequence_number: 1,
          display_name: 'a.jpg',
          client_file_id: null,
          upload_cancel_requested: 0,
        }),
        getSession: async () => ({
          id: 's1',
          preparation_processing_mode: 'CODE_SCAN',
          inventory_id: 'inv',
          aisle_id: 'aisle',
        }),
      } as never,
      draftRepo: { getBySessionAndPhotoId, listForSession: async () => [] } as never,
      localCodeScan: {
        execute: jest.fn(async () => undefined),
      } as never,
      localCodeScanEnabled: true,
    });

    queue.setStageObserver({
      onStage: (e) => {
        const row: {
          stage: string;
          durationMs: number;
          extras?: Record<string, unknown>;
        } = {
          stage: e.stage,
          durationMs: e.durationMs,
        };
        if (e.extras) {
          row.extras = e.extras as Record<string, unknown>;
        }
        stages.push(row);
      },
    });

    await (queue as unknown as { processJob: (j: typeof job) => Promise<void> }).processJob(job);
    queue.stop();

    const pre = stages.filter((s) => s.stage === 'draft_lookup_pre_scan');
    const post = stages.filter((s) => s.stage === 'draft_lookup_post_scan');
    const alias = stages.filter((s) => s.stage === 'draft_lookup');
    expect(pre.length).toBe(1);
    expect(post.length).toBe(1);
    expect(alias.length).toBe(2);
    expect(pre[0]!.extras?.lookupPurpose).toBe('skip_scan_check');
    expect(post[0]!.extras?.lookupPurpose).toBe('export_ready_check');
    expect(lookupCalls).toBe(2);
    expect(alias.every((s) => Number(s.extras?.queryCount) === 1)).toBe(true);

    // Timer must not include the slow countsForSession (~40ms) used only at job end.
    for (const s of [...pre, ...post, ...alias]) {
      expect(s.durationMs).toBeLessThan(35);
    }
    expect(countsCalls).toBeGreaterThanOrEqual(1);
  });
});
