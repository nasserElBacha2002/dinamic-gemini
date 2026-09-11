import { describe, expect, it, beforeEach } from '@jest/globals';
import {
  applyPositionScan,
  clearAllActivePositions,
  clearInMemoryPositionState,
  getActivePosition,
  hydratePositionSessionFromDrafts,
  resetPositionSession,
  preparePositionActivation,
  commitPositionActivation,
} from '../src/features/localCodeScan/activePositionStore';
import {
  classifyDinamicPositionPayload,
  formatMarkerPair,
  parseDinamicPositionPayload,
  parseActivePositionStateJson,
  createActivePositionState,
  normalizeLocalPositionCode,
  serializeActivePositionState,
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
    expect(active?.validationStatus).toBe('STRUCTURALLY_VALID');
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
    const reactivatedPos1 = applyPositionScan('sess-dedupe', pos1);
    expect(reactivatedPos1.kind).toBe('applied');
    expect(getActivePosition('sess-dedupe')?.labelId).toBe('POS001');
  });

  it('rehydrates seen position ids from persisted drafts after in-memory loss', () => {
    const pos1 = v2Payload({ label_id: 'POS001', pallet: '04', side: 'RIGHT' });
    const pos2 = v2Payload({ label_id: 'POS002', pallet: '05', side: 'LEFT' });
    expect(applyPositionScan('sess-restart', pos1).kind).toBe('applied');
    const snap1 = getActivePosition('sess-restart')!;
    expect(applyPositionScan('sess-restart', pos2).kind).toBe('applied');
    const snap2 = getActivePosition('sess-restart')!;
    const parsedSnapshot = parseActivePositionStateJson(JSON.stringify(snap2), {
      captureSessionId: 'sess-restart',
      inventoryId: null,
      aisleLocalId: null,
    });
    if (!parsedSnapshot.ok) throw new Error(parsedSnapshot.errorCode);

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
    expect(applyPositionScan('sess-restart', pos1).kind).toBe('applied');
    expect(getActivePosition('sess-restart')?.labelId).toBe('POS001');
  });

  it('allows same position label in a different capture session after rehydration', () => {
    const pos1 = v2Payload({ label_id: 'POS001', pallet: '04', side: 'RIGHT' });
    applyPositionScan('sess-a', pos1);
    clearInMemoryPositionState('sess-a');
    hydratePositionSessionFromDrafts('sess-b', []);
    expect(applyPositionScan('sess-b', pos1).kind).toBe('applied');
  });

  it('round-trips a supplier V2 position without remote ids', () => {
    const rawCode = '  supplier-a  ';
    const rawPayload = '\n supplier-payload \t';
    const supplier = createActivePositionState({
      localRecognitionId: 'local-supplier-1',
      captureSessionId: 'session-supplier',
      inventoryId: 'inventory-1',
      aisleLocalId: 'aisle-1',
      rawCode,
      rawPayload,
      source: 'LOCAL_CODE_SCAN',
      profileId: 'profile-1',
      profileVersion: 3,
      clientSupplierId: 'supplier-1',
    });
    expect(supplier.normalizedCode).toBe('SUPPLIER-A');
    expect(supplier.rawCode).toBe(rawCode);
    expect(supplier.rawPayload).toBe(rawPayload);
    expect(supplier.remotePositionId).toBeNull();
    expect(supplier.signatureEvidence.verification).toBe('MISSING');

    const restored = parseActivePositionStateJson(JSON.stringify(supplier), {
      captureSessionId: 'session-supplier',
      inventoryId: 'inventory-1',
      aisleLocalId: 'aisle-1',
    });
    expect(restored.ok).toBe(true);
    if (!restored.ok) throw new Error(restored.errorCode);
    expect(restored.state.rawCode).toBe(rawCode);
    expect(restored.state.rawPayload).toBe(rawPayload);
    expect(restored.state.normalizedCode).toBe('SUPPLIER-A');
    expect(JSON.parse(serializeActivePositionState(restored.state))).toMatchObject({
      rawCode,
      rawPayload,
      normalizedCode: 'SUPPLIER-A',
    });
    const activation = preparePositionActivation(supplier);
    commitPositionActivation(activation);
    expect(getActivePosition('session-supplier')?.clientSupplierId).toBe('supplier-1');
    const otherSupplier = createActivePositionState({
      ...supplier,
      localRecognitionId: 'local-supplier-2',
      rawPayload: supplier.rawPayload,
      clientSupplierId: 'supplier-2',
    });
    const supplierTransition = preparePositionActivation(otherSupplier);
    expect(supplierTransition.kind).toBe('applied');
  });

  it.each([
    [' spaces and casing ', 'SPACES AND CASING'],
    ['po\u0301s-a', 'PÓS-A'],
    ['x'.repeat(64), 'X'.repeat(64)],
  ])('uses canonical position normalization for %s', (input, expected) => {
    expect(normalizeLocalPositionCode(input)).toBe(expected);
  });

  it.each(['', '\u0000POS-A', 'x'.repeat(65)])(
    'rejects invalid canonical position code without corrupting state',
    (input) => {
      expect(() => normalizeLocalPositionCode(input)).toThrow();
      expect(getActivePosition('invalid-session')).toBeNull();
    },
  );

  it('compares persisted NFC/NFD codes canonically and stores NFC', () => {
    const state = createActivePositionState({
      localRecognitionId: 'unicode-position',
      captureSessionId: 'unicode-session',
      inventoryId: 'inventory-1',
      aisleLocalId: 'aisle-1',
      rawCode: 'pós-a',
      rawPayload: 'pós-a',
      source: 'LOCAL_CODE_SCAN',
    });
    const persisted = {
      ...state,
      labelId: 'PO\u0301S-A',
      normalizedCode: 'po\u0301s-a',
    };
    const parsed = parseActivePositionStateJson(JSON.stringify(persisted), {
      captureSessionId: 'unicode-session',
      inventoryId: 'inventory-1',
      aisleLocalId: 'aisle-1',
    });
    expect(parsed.ok).toBe(true);
    if (parsed.ok) expect(parsed.state.normalizedCode).toBe('PÓS-A');
  });

  it('rejects corrupt persisted state without throwing', () => {
    expect(
      parseActivePositionStateJson('{broken', {
        captureSessionId: 'session-1',
        inventoryId: 'inventory-1',
        aisleLocalId: 'aisle-1',
      }),
    ).toEqual({ ok: false, errorCode: 'ACTIVE_POSITION_JSON_INVALID' });
  });

  it('migrates a legacy active_position_json without requiring reinstall', () => {
    const raw = `  ${v2Payload({ label_id: 'LEGACY-POS' })}\n`;
    const parsed = parseActivePositionStateJson(
      JSON.stringify({
        labelId: 'LEGACY-POS',
        positionLabelId: 'LEGACY-POS',
        rawPayload: raw,
        sourcePayload: raw,
      }),
      {
        captureSessionId: 'legacy-session',
        inventoryId: 'inventory-1',
        aisleLocalId: 'aisle-1',
      },
    );
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.migrated).toBe(true);
    expect(parsed.state.schemaVersion).toBe(2);
    expect(parsed.state.normalizedCode).toBe('LEGACY-POS');
    expect(parsed.state.rawCode).toBe(raw);
    expect(parsed.state.rawPayload).toBe(raw);
  });
});
