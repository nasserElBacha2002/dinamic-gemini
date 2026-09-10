import { readFileSync } from 'node:fs';
import path from 'node:path';

import { parsePositionSyncResultV2 } from '../src/features/preliminarySync/preliminaryDetectionApi';

const contractRoot = path.resolve(__dirname, '../../contracts/position-sync/v2');

function result(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    contract_version: 2,
    local_recognition_id: 'local-position-1',
    normalized_code: 'POS-A',
    remote_position_id: null,
    remote_position_label_id: null,
    status: 'ACCEPTED_UNMATERIALIZED',
    error_code: null,
    retryable: false,
    server_timestamp: '2026-07-24T12:00:01.000Z',
    reconciliation_revision: 1,
    ...overrides,
  };
}

describe('position sync V2 shared contract', () => {
  it('accepts the shared authoritative response', () => {
    const response: unknown = JSON.parse(
      readFileSync(
        path.join(contractRoot, 'response-accepted-unmaterialized.json'),
        'utf8',
      ),
    );
    if (typeof response !== 'object' || response === null || Array.isArray(response)) {
      throw new Error('invalid fixture');
    }

    expect(
      parsePositionSyncResultV2(
        (response as Record<string, unknown>).position_result,
      ),
    ).toMatchObject({
      local_recognition_id: 'local-position-1',
      status: 'ACCEPTED_UNMATERIALIZED',
      remote_position_id: null,
    });
  });

  it('rejects unknown statuses and incompatible versions', () => {
    expect(
      parsePositionSyncResultV2({
        contract_version: 99,
        local_recognition_id: 'local-position-1',
        status: 'UNKNOWN',
      }),
    ).toBeNull();
  });

  it.each([
    ['MATERIALIZED', true, false],
    ['REUSED', false, true],
  ] as const)('parses %s with authoritative ids', (status, created, replay) => {
    expect(
      parsePositionSyncResultV2({
        contract_version: 2,
        local_recognition_id: 'local-position-1',
        normalized_code: 'POS-A',
        remote_position_id: 'loc_public_1',
        remote_position_label_id: 'label-1',
        status,
        error_code: null,
        retryable: false,
        server_timestamp: '2026-07-24T12:00:01.000Z',
        reconciliation_revision: 1,
        created,
        idempotent_replay: replay,
      }),
    ).toMatchObject({
      status,
      remote_position_id: 'loc_public_1',
      remote_position_label_id: 'label-1',
      created,
      idempotent_replay: replay,
    });
  });

  it('rejects accepted materialization without a position id', () => {
    expect(
      parsePositionSyncResultV2({
        contract_version: 2,
        local_recognition_id: 'local-position-1',
        normalized_code: 'POS-A',
        remote_position_id: null,
        remote_position_label_id: null,
        status: 'MATERIALIZED',
        error_code: null,
        retryable: false,
        server_timestamp: '2026-07-24T12:00:01.000Z',
        reconciliation_revision: 1,
      }),
    ).toBeNull();
  });

  it.each([
    'REJECTED_VALIDATION',
    'REJECTED_CONFLICT',
    'REJECTED_DUPLICATE',
    'REJECTED_SCOPE',
    'INVARIANT_VIOLATION',
  ] as const)('preserves explicit backend taxonomy for %s', (status) => {
    expect(parsePositionSyncResultV2(result({ status }))).toMatchObject({ status });
  });

  it('enforces retry, creation, and replay invariants', () => {
    expect(
      parsePositionSyncResultV2(result({ status: 'RETRYABLE_ERROR', retryable: false })),
    ).toBeNull();
    expect(parsePositionSyncResultV2(result({ retryable: true }))).toBeNull();
    expect(parsePositionSyncResultV2(result({ created: true }))).toBeNull();
    expect(
      parsePositionSyncResultV2(
        result({
          status: 'MATERIALIZED',
          remote_position_id: 'position-1',
          created: true,
          idempotent_replay: true,
        }),
      ),
    ).toBeNull();
    expect(
      parsePositionSyncResultV2(
        result({ status: 'REUSED', remote_position_id: 'position-1' }),
      ),
    ).toMatchObject({ created: false, idempotent_replay: false });
  });

  it.each([
    [' spaces and casing ', 'SPACES AND CASING'],
    ['po\u0301s-a', 'PÓS-A'],
    ['x'.repeat(64), 'X'.repeat(64)],
  ])('canonicalizes valid normalized code %s', (input, expected) => {
    expect(parsePositionSyncResultV2(result({ normalized_code: input }))).toMatchObject({
      normalized_code: expected,
    });
  });

  it.each(['', '\u0000POS-A', 'x'.repeat(65)])(
    'fails closed for invalid normalized code',
    (normalizedCode) => {
      expect(
        parsePositionSyncResultV2(result({ normalized_code: normalizedCode })),
      ).toBeNull();
    },
  );

  it('retains created and replay in parsed server JSON without SQLite fields', () => {
    const parsed = parsePositionSyncResultV2(
      result({
        status: 'MATERIALIZED',
        remote_position_id: 'position-1',
        created: false,
        idempotent_replay: true,
      }),
    );
    expect(parsed).toMatchObject({ created: false, idempotent_replay: true });
  });
});
