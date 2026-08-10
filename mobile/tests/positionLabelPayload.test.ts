import { describe, expect, it } from '@jest/globals';
import {
  applyPositionScan,
  clearActivePosition,
  getActivePosition,
} from '../src/features/localCodeScan/activePositionStore';
import {
  formatMarkerPair,
  parseDinamicPositionPayload,
} from '../src/core/positionLabelPayload';

describe('positionLabelPayload', () => {
  it('formats 01/03', () => {
    expect(formatMarkerPair(1, 3)).toBe('01/03');
    expect(formatMarkerPair(2, 12)).toBe('02/12');
  });

  it('parses v2 hierarchy', () => {
    const raw = JSON.stringify({
      type: 'DINAMIC_POSITION',
      version: 2,
      label_id: 'pos_abc',
      pallet: '12',
      side: 'LEFT',
      level: 3,
      marker_index: 1,
      marker_total: 3,
    });
    const parsed = parseDinamicPositionPayload(raw);
    expect(parsed?.formattedMarker).toBe('01/03');
    expect(parsed?.displayName).toContain('LEFT');
    expect(parsed?.canonicalKey).toBe('12|LEFT|3|1|3');
  });

  it('sets active position from scan', () => {
    clearActivePosition();
    const raw = JSON.stringify({
      type: 'DINAMIC_POSITION',
      version: 2,
      label_id: 'pos_xyz',
      pallet: '1',
      side: 'RIGHT',
      level: 2,
      marker_index: 2,
      marker_total: 2,
    });
    const active = applyPositionScan(raw);
    expect(active?.formattedMarker).toBe('02/02');
    expect(getActivePosition()?.labelId).toBe('pos_xyz');
    clearActivePosition();
  });
});
