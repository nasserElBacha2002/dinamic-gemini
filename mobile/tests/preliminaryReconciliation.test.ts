/**
 * Phase 5 — reconciliation outcome labels and compare alignment.
 */
import { compareLocalVsServer } from '../src/features/localCodeScan/localCodeScanStrategy';
import { reconciliationOutcomeLabel } from '../src/features/preliminaryReconciliation/reconciliationQueryService';
import { resolveFeatureFlags, DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

describe('Phase 5 reconciliation compare outcomes', () => {
  it('uses REMOTE_ONLY (not SERVER_ONLY)', () => {
    expect(
      compareLocalVsServer({
        localInternalCode: null,
        localQuantity: null,
        localStatus: 'UNRESOLVED',
        serverInternalCode: 'X',
        serverQuantity: 1,
        mappingReliable: true,
      }),
    ).toBe('REMOTE_ONLY');
  });

  it('distinguishes quantity missing variants', () => {
    expect(
      compareLocalVsServer({
        localInternalCode: 'A',
        localQuantity: null,
        localStatus: 'RESOLVED',
        serverInternalCode: 'A',
        serverQuantity: null,
        mappingReliable: true,
      }),
    ).toBe('MATCH_CODE_BOTH_QUANTITY_MISSING');
  });

  it('labels are diagnostic Spanish', () => {
    expect(reconciliationOutcomeLabel('CODE_MISMATCH')).toBe('Código diferente');
    expect(reconciliationOutcomeLabel('NOT_COMPARABLE')).toBe('No comparable');
  });

  it('reconciliation view flag defaults false', () => {
    const flags = resolveFeatureFlags({}, 'production');
    expect(flags.mobilePreliminaryReconciliationView).toBe(false);
    expect(DEFAULT_FEATURE_FLAGS.mobilePreliminaryReconciliationView).toBe(false);
  });
});
