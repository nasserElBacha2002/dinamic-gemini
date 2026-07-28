/**
 * Phase 9 — pure offline operation core (retry, deps, payloads, projection).
 */
import {
  buildIdempotencyKey,
  classifyHttpOrNetworkError,
} from '../src/features/offlineOperations/offlineOperationTypes';
import {
  recoverAbandonedRunningStatus,
  selectEligibleOperations,
  dependenciesSatisfied,
} from '../src/features/offlineOperations/offlineDependencyResolver';
import {
  computeBackoffMs,
  nextRetryIso,
  OFFLINE_RETRY_SCHEDULE_MS,
} from '../src/features/offlineOperations/offlineRetryPolicy';
import {
  encodePayload,
  decodeUploadAssetPayloadV1,
  decodeFinalizeAislePayloadV1,
} from '../src/features/offlineOperations/offlinePayloads';
import {
  buildAisleSessionProjection,
  getPrimaryAisleAction,
} from '../src/features/offlineOperations/aisleSessionProjection';
import type { OfflineOperationRow } from '../src/features/offlineOperations/offlineOperationTypes';

function row(partial: Partial<OfflineOperationRow> & Pick<OfflineOperationRow, 'operation_id'>): OfflineOperationRow {
  return {
    operation_type: 'UPLOAD_ASSET',
    entity_type: 'asset',
    entity_id: 'a1',
    inventory_id: 'inv',
    aisle_id: 'aisle',
    asset_id: 'asset',
    session_id: 'sess',
    payload_json: '{}',
    payload_version: 1,
    payload_hash: null,
    idempotency_key: `upload:${partial.operation_id}`,
    status: 'READY',
    priority: 40,
    attempt_count: 0,
    max_attempts: 12,
    next_retry_at: null,
    last_attempt_at: null,
    last_error_code: null,
    last_error_message: null,
    requires_network: 1,
    requires_auth: 1,
    owner_token: null,
    lease_expires_at: null,
    heartbeat_at: null,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    completed_at: null,
    ...partial,
  };
}

describe('offline retry policy', () => {
  it('uses exponential schedule with jitter bounded by 20%', () => {
    const base = OFFLINE_RETRY_SCHEDULE_MS[0]!;
    const withZeroJitter = computeBackoffMs(0, OFFLINE_RETRY_SCHEDULE_MS, () => 0);
    const withMaxJitter = computeBackoffMs(0, OFFLINE_RETRY_SCHEDULE_MS, () => 0.999);
    expect(withZeroJitter).toBe(base);
    expect(withMaxJitter).toBeGreaterThanOrEqual(base);
    expect(withMaxJitter).toBeLessThan(base + base * 0.2 + 1);
  });

  it('advances schedule by attempt index', () => {
    expect(computeBackoffMs(0, OFFLINE_RETRY_SCHEDULE_MS, () => 0)).toBe(5_000);
    expect(computeBackoffMs(3, OFFLINE_RETRY_SCHEDULE_MS, () => 0)).toBe(120_000);
    expect(computeBackoffMs(99, OFFLINE_RETRY_SCHEDULE_MS, () => 0)).toBe(3_600_000);
  });

  it('builds next_retry_at ISO after backoff', () => {
    const iso = nextRetryIso(Date.parse('2026-01-01T00:00:00.000Z'), 0, () => 0);
    expect(iso).toBe('2026-01-01T00:00:05.000Z');
  });
});

describe('offline error classification', () => {
  it('classifies auth / conflict / terminal / retryable', () => {
    expect(classifyHttpOrNetworkError({ httpStatus: 401 })).toBe('auth');
    expect(classifyHttpOrNetworkError({ httpStatus: 409 })).toBe('conflict');
    expect(classifyHttpOrNetworkError({ code: 'STALE_REVISION' })).toBe('conflict');
    expect(classifyHttpOrNetworkError({ httpStatus: 404 })).toBe('terminal');
    expect(classifyHttpOrNetworkError({ code: 'LOCAL_FILE_HASH_MISMATCH' })).toBe('terminal');
    expect(classifyHttpOrNetworkError({ httpStatus: 503 })).toBe('retryable');
    expect(classifyHttpOrNetworkError({ message: 'network timeout' })).toBe('retryable');
  });
});

describe('offline dependencies', () => {
  it('blocks until parents COMPLETED', () => {
    const parent = row({ operation_id: 'p1', status: 'READY' });
    const child = row({
      operation_id: 'c1',
      operation_type: 'SYNC_AUTHORITATIVE_RESULT',
      status: 'READY',
    });
    const edges = [{ operation_id: 'c1', depends_on_operation_id: 'p1' }];
    const byId = new Map([
      [parent.operation_id, parent],
      [child.operation_id, child],
    ]);
    expect(dependenciesSatisfied('c1', edges, byId).ok).toBe(false);

    const done = row({ operation_id: 'p1', status: 'COMPLETED' });
    byId.set('p1', done);
    expect(dependenciesSatisfied('c1', edges, byId).ok).toBe(true);
  });

  it('selects eligible ops respecting network, auth, retry_wait, priority', () => {
    const ops = [
      row({ operation_id: 'a', status: 'READY', priority: 80, requires_network: 1 }),
      row({
        operation_id: 'b',
        status: 'RETRY_WAIT',
        priority: 40,
        next_retry_at: '2099-01-01T00:00:00.000Z',
      }),
      row({ operation_id: 'c', status: 'READY', priority: 40, requires_auth: 1 }),
      row({ operation_id: 'd', status: 'BLOCKED_AUTH', priority: 10 }),
    ];
    const eligible = selectEligibleOperations({
      operations: ops,
      edges: [],
      nowIso: '2026-01-01T00:00:00.000Z',
      hasNetwork: true,
      hasAuth: false,
      limit: 10,
    });
    expect(eligible.map((o) => o.operation_id)).toEqual([]);

    const withAuth = selectEligibleOperations({
      operations: ops,
      edges: [],
      nowIso: '2026-01-01T00:00:00.000Z',
      hasNetwork: true,
      hasAuth: true,
      limit: 10,
    });
    expect(withAuth.map((o) => o.operation_id)).toEqual(['c', 'a']);
  });

  it('recovers abandoned RUNNING → READY', () => {
    expect(recoverAbandonedRunningStatus('RUNNING')).toBe('READY');
    expect(recoverAbandonedRunningStatus('READY')).toBeNull();
  });
});

describe('offline payloads', () => {
  it('round-trips upload payload and rejects invalid', () => {
    const payload = {
      localFilePath: '/tmp/a.jpg',
      assetId: 'asset-1',
      capturePhotoId: 'photo-1',
      sha256: 'abc',
      preparedMimeType: 'image/jpeg',
      byteSize: 12,
      sessionId: 's',
      inventoryId: 'i',
      aisleId: 'a',
    };
    const json = encodePayload(payload);
    expect(decodeUploadAssetPayloadV1(json)).toEqual(payload);
    expect(() => decodeUploadAssetPayloadV1('{"localFilePath":""}')).toThrow(/INVALID_PAYLOAD/);
  });

  it('decodes finalize payload', () => {
    const payload = {
      sessionId: 's',
      inventoryId: 'i',
      aisleId: 'a',
      finalizationId: 'f1',
      expectedAssetCount: 3,
      baseReadinessVersion: 'v1',
    };
    expect(decodeFinalizeAislePayloadV1(encodePayload(payload))).toEqual(payload);
  });

  it('builds stable idempotency keys', () => {
    expect(buildIdempotencyKey('UPLOAD_ASSET', ['a', 'hash'])).toBe('upload:a:hash');
    expect(buildIdempotencyKey('FINALIZE_AISLE', ['fid'])).toBe('finalize:fid');
    expect(buildIdempotencyKey('START_SERVER_PROCESSING', ['aisle', 'pv', 'req'])).toBe(
      'process:aisle:pv:req',
    );
  });
});

describe('aisle session projection', () => {
  it('derives primary action without exposing internal statuses', () => {
    const action = getPrimaryAisleAction({
      captureActive: false,
      hasNetwork: true,
      pendingUploads: 2,
      runningUploads: 0,
      pendingSyncs: 0,
      pendingFinalizations: 0,
      blockedAuth: 0,
      conflicts: 0,
      reviewCount: 0,
      hasStartServerOp: false,
    });
    expect(action.kind).toBe('retry_uploads');
    expect(action.label).toContain('2');

    const proj = buildAisleSessionProjection({
      sessionId: 's',
      inventoryId: 'i',
      aisleId: 'a',
      operations: [
        row({ operation_id: '1', status: 'FAILED_TERMINAL' }),
        row({ operation_id: '2', status: 'READY', operation_type: 'UPLOAD_ASSET' }),
      ],
      nowMs: Date.parse('2026-01-01T01:00:00.000Z'),
      hasNetwork: true,
    });
    expect(proj.userStatusLabel).toBe('Falló');
    expect(proj.primaryAction.kind).toBe('attention');
    expect(JSON.stringify(proj)).not.toMatch(/RETRY_WAIT|BLOCKED_DEPENDENCY/);
  });

  it('does not offer retry uploads while RUNNING', () => {
    const action = getPrimaryAisleAction({
      captureActive: false,
      hasNetwork: true,
      pendingUploads: 2,
      runningUploads: 1,
      pendingSyncs: 0,
      pendingFinalizations: 0,
      blockedAuth: 0,
      conflicts: 0,
      reviewCount: 0,
      hasStartServerOp: false,
    });
    expect(action.kind).not.toBe('retry_uploads');
  });
});

describe('payload hash', () => {
  it('changes when payload changes for same logical key inputs', () => {
    const { computeOfflinePayloadHash } = require('../src/features/offlineOperations/offlinePayloadHash');
    const a = computeOfflinePayloadHash({
      operationType: 'UPLOAD_ASSET',
      entityType: 'asset',
      entityId: 'a1',
      payloadVersion: 1,
      payloadJson: JSON.stringify({ x: 1 }),
      dependsOnOperationIds: [],
    });
    const b = computeOfflinePayloadHash({
      operationType: 'UPLOAD_ASSET',
      entityType: 'asset',
      entityId: 'a1',
      payloadVersion: 1,
      payloadJson: JSON.stringify({ x: 2 }),
      dependsOnOperationIds: [],
    });
    expect(a).not.toBe(b);
  });
});
