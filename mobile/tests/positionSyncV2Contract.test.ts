import { readFileSync } from 'node:fs';
import path from 'node:path';

import { parsePositionSyncResultV2 } from '../src/features/preliminarySync/preliminaryDetectionApi';

const contractRoot = path.resolve(__dirname, '../../contracts/position-sync/v2');

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
});
