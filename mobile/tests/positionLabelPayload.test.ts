import { describe, expect, it, beforeEach } from '@jest/globals';
import {
  applyPositionScan,
  clearActivePosition,
  clearAllActivePositions,
  getActivePosition,
} from '../src/features/localCodeScan/activePositionStore';
import {
  classifyDinamicPositionPayload,
  formatMarkerPair,
  parseDinamicPositionPayload,
} from '../src/core/positionLabelPayload';

const v2Payload = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    type: 'DINAMIC_POSITION',
    version: 2,
    label_id: 'pos_abc',
    pallet: '12',
    side: 'LEFT',
    level: 3,
    marker_index: 1,
    marker_total: 3,
    ...over,
  });

describe('positionLabelPayload', () => {
  beforeEach(() => {
    clearAllActivePositions();
  });

  it('formats 01/03', () => {
    expect(formatMarkerPair(1, 3)).toBe('01/03');
    expect(formatMarkerPair(2, 12)).toBe('02/12');
  });

  it('parses signed generator-shaped v2 QR as STRUCTURALLY_VALID_UNVERIFIED', () => {
    // Mirrors backend canonicalize_positioning_payload (sorted keys, no spaces).
    const raw =
      '{"key_version":1,"label_id":"pos_golden_v2_01","level":2,"marker_index":1,' +
      '"marker_total":3,"pallet":"04","side":"LEFT","signature":"abc123deadbeef",' +
      '"type":"DINAMIC_POSITION","version":2}';
    const parsed = parseDinamicPositionPayload(raw);
    expect(parsed).not.toBeNull();
    expect(parsed?.validationStatus).toBe('STRUCTURALLY_VALID_UNVERIFIED');
    expect(parsed?.labelId).toBe('pos_golden_v2_01');
    expect(parsed?.formattedMarker).toBe('01/03');
    expect(parsed?.signature).toBe('abc123deadbeef');
  });

  it('rejects invalid hierarchy', () => {
    const raw = v2Payload({ marker_index: 5, marker_total: 3 });
    expect(parseDinamicPositionPayload(raw)).toBeNull();
    expect(classifyDinamicPositionPayload(raw)).toBe('INVALID_FORMAT');
  });

  it('classifies unknown version', () => {
    const raw = v2Payload({ version: 99 });
    expect(parseDinamicPositionPayload(raw)).toBeNull();
    expect(classifyDinamicPositionPayload(raw)).toBe('UNKNOWN_VERSION');
  });

  it('keeps active position session-scoped (A does not leak to B)', () => {
    const rawA = v2Payload({ label_id: 'POS-A', pallet: '1' });
    applyPositionScan('session-A', rawA);
    expect(getActivePosition('session-A')?.positionLabelId).toBe('POS-A');
    expect(getActivePosition('session-B')).toBeNull();
    clearActivePosition('session-A');
    expect(getActivePosition('session-A')).toBeNull();
  });

  it('applyPositionScan is session scoped', () => {
    const raw = v2Payload({ label_id: 'pos_xyz', pallet: '1', side: 'RIGHT', level: 2, marker_index: 2, marker_total: 2 });
    const active = applyPositionScan('sess-1', raw);
    expect(active?.formattedMarker).toBe('02/02');
    expect(active?.validationStatus).toBe('STRUCTURALLY_VALID_UNVERIFIED');
    expect(active?.rawPayload).toBe(raw);
    expect(getActivePosition('sess-1')?.labelId).toBe('pos_xyz');
    expect(getActivePosition('other')).toBeNull();
  });
});
