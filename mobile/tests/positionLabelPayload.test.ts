import { describe, expect, it, beforeEach } from '@jest/globals';
import {
  applyPositionScan,
  clearAllActivePositions,
  clearInMemoryPositionState,
  getActivePosition,
  hydratePositionSessionFromDrafts,
  resetPositionSession,
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
    const result = applyPositionScan('session-A', rawA);
    expect(result.kind).toBe('applied');
    expect(getActivePosition('session-A')?.positionLabelId).toBe('POS-A');
    expect(getActivePosition('session-B')).toBeNull();
    resetPositionSession('session-A');
    expect(getActivePosition('session-A')).toBeNull();
  });

  it('applyPositionScan is session scoped', () => {
    const raw = v2Payload({ label_id: 'pos_xyz', pallet: '1', side: 'RIGHT', level: 2, marker_index: 2, marker_total: 2 });
    const result = applyPositionScan('sess-1', raw);
    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') throw new Error('expected applied');
    const active = result.state;
    expect(active?.formattedMarker).toBe('02/02');
    expect(active?.validationStatus).toBe('STRUCTURALLY_VALID_UNVERIFIED');
    expect(active?.rawPayload).toBe(raw);
    expect(getActivePosition('sess-1')?.labelId).toBe('pos_xyz');
    expect(getActivePosition('other')).toBeNull();
  });

  it('rejects duplicate position.label_id within session; allows different positions', () => {
    const pos1 = v2Payload({ label_id: 'POS001', pallet: '04', side: 'RIGHT' });
    const pos2 = v2Payload({ label_id: 'POS002', pallet: '05', side: 'LEFT' });
    expect(applyPositionScan('sess-dedupe', pos1).kind).toBe('applied');
    expect(applyPositionScan('sess-dedupe', pos2).kind).toBe('applied');
    expect(getActivePosition('sess-dedupe')?.labelId).toBe('POS002');
    const dup = applyPositionScan('sess-dedupe', pos2);
    expect(dup.kind).toBe('duplicate');
    if (dup.kind !== 'duplicate') throw new Error('expected duplicate');
    expect(dup.state.labelId).toBe('POS002');
    const dupPos1 = applyPositionScan('sess-dedupe', pos1);
    expect(dupPos1.kind).toBe('duplicate');
  });

  it('rehydrates seen position ids from persisted drafts after in-memory loss', () => {
    const pos1 = v2Payload({ label_id: 'POS001', pallet: '04', side: 'RIGHT' });
    const pos2 = v2Payload({ label_id: 'POS002', pallet: '05', side: 'LEFT' });
    expect(applyPositionScan('sess-restart', pos1).kind).toBe('applied');
    const snap1 = getActivePosition('sess-restart')!;
    expect(applyPositionScan('sess-restart', pos2).kind).toBe('applied');
    const snap2 = getActivePosition('sess-restart')!;

    clearInMemoryPositionState('sess-restart');
    expect(getActivePosition('sess-restart')).toBeNull();

    hydratePositionSessionFromDrafts('sess-restart', [
      {
        position_detected: 1,
        position_snapshot_json: JSON.stringify(snap1),
        updated_at: '2026-08-10T00:00:01Z',
      },
      {
        position_detected: 1,
        position_snapshot_json: JSON.stringify(snap2),
        updated_at: '2026-08-10T00:00:02Z',
      },
    ]);

    expect(getActivePosition('sess-restart')?.labelId).toBe('POS002');
    expect(applyPositionScan('sess-restart', pos1).kind).toBe('duplicate');
    expect(getActivePosition('sess-restart')?.labelId).toBe('POS002');
  });

  it('allows same position label in a different capture session after rehydration', () => {
    const pos1 = v2Payload({ label_id: 'POS001', pallet: '04', side: 'RIGHT' });
    applyPositionScan('sess-a', pos1);
    clearInMemoryPositionState('sess-a');
    hydratePositionSessionFromDrafts('sess-b', []);
    expect(applyPositionScan('sess-b', pos1).kind).toBe('applied');
  });
});
