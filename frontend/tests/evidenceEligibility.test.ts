/**
 * Phase 4.2 — evidence display eligibility tests.
 */

import { describe, it, expect } from 'vitest';
import { isEvidenceDisplayable, isLegacyEvidenceDisplayable } from '../src/features/results/utils/evidenceEligibility';
import { evidenceUnavailableMessageKey } from '../src/features/results/utils/evidenceUnavailableMessage';

describe('isEvidenceDisplayable', () => {
  it('returns false without evidenceView unless legacy fallback is explicitly allowed', () => {
    expect(isEvidenceDisplayable('VALID', true, 'asset-1')).toBe(false);
    expect(
      isEvidenceDisplayable('VALID', true, 'asset-1', null, {
        allowLegacyEvidenceFallback: true,
      })
    ).toBe(true);
  });

  it('returns false for INVALID even with legacy fallback', () => {
    expect(isEvidenceDisplayable('INVALID', true, 'asset-1')).toBe(false);
    expect(isEvidenceDisplayable('INVALID', false, 'asset-1')).toBe(false);
  });

  it('returns false for MISSING and UNVALIDATED with legacy fallback', () => {
    const opts = { allowLegacyEvidenceFallback: true as const };
    expect(isEvidenceDisplayable('MISSING', true, 'asset-1', null, opts)).toBe(false);
    expect(isEvidenceDisplayable('UNVALIDATED', true, 'asset-1', null, opts)).toBe(false);
  });

  it('returns false when hasValidEvidence is not true (legacy path)', () => {
    const opts = { allowLegacyEvidenceFallback: true as const };
    expect(isEvidenceDisplayable('VALID', false, 'asset-1', null, opts)).toBe(false);
    expect(isEvidenceDisplayable('VALID', undefined, 'asset-1', null, opts)).toBe(false);
  });

  it('returns false when sourceImageId is empty (legacy path)', () => {
    const opts = { allowLegacyEvidenceFallback: true as const };
    expect(isEvidenceDisplayable('VALID', true, null, null, opts)).toBe(false);
    expect(isEvidenceDisplayable('VALID', true, '  ', null, opts)).toBe(false);
  });

  it('Phase 4.8: structural evidenceView.displayable overrides legacy fields', () => {
    expect(
      isEvidenceDisplayable('VALID', true, 'asset-1', {
        displayable: false,
        traceabilityStatus: 'invalid',
        sourceKind: 'structural_result_evidence',
      })
    ).toBe(false);

    expect(
      isEvidenceDisplayable('INVALID', false, null, {
        displayable: true,
        traceabilityStatus: 'valid',
        sourceKind: 'structural_result_evidence',
      })
    ).toBe(true);
  });
});

describe('isLegacyEvidenceDisplayable', () => {
  it('matches legacy Phase 4.2 rules', () => {
    expect(isLegacyEvidenceDisplayable('VALID', true, 'asset-1')).toBe(true);
    expect(isLegacyEvidenceDisplayable('VALID', false, 'asset-1')).toBe(false);
  });
});

describe('evidenceUnavailableMessageKey', () => {
  it('maps statuses to i18n keys', () => {
    expect(evidenceUnavailableMessageKey('MISSING')).toBe(
      'results.evidence_panel.unavailable_missing'
    );
    expect(evidenceUnavailableMessageKey('INVALID')).toBe(
      'results.evidence_panel.unavailable_invalid'
    );
    expect(evidenceUnavailableMessageKey('UNVALIDATED')).toBe(
      'results.evidence_panel.unavailable_unvalidated'
    );
  });
});
