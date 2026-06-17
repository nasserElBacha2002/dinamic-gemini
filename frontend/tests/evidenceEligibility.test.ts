/**
 * Phase 4.2 — evidence display eligibility tests.
 */

import { describe, it, expect } from 'vitest';
import { isEvidenceDisplayable } from '../src/features/results/utils/evidenceEligibility';
import { evidenceUnavailableMessageKey } from '../src/features/results/utils/evidenceUnavailableMessage';

describe('isEvidenceDisplayable', () => {
  it('returns true only for VALID with hasValidEvidence and sourceImageId', () => {
    expect(isEvidenceDisplayable('VALID', true, 'asset-1')).toBe(true);
  });

  it('returns false for INVALID even with sourceImageId', () => {
    expect(isEvidenceDisplayable('INVALID', true, 'asset-1')).toBe(false);
    expect(isEvidenceDisplayable('INVALID', false, 'asset-1')).toBe(false);
  });

  it('returns false for MISSING and UNVALIDATED', () => {
    expect(isEvidenceDisplayable('MISSING', true, 'asset-1')).toBe(false);
    expect(isEvidenceDisplayable('UNVALIDATED', true, 'asset-1')).toBe(false);
  });

  it('returns false when hasValidEvidence is not true', () => {
    expect(isEvidenceDisplayable('VALID', false, 'asset-1')).toBe(false);
    expect(isEvidenceDisplayable('VALID', undefined, 'asset-1')).toBe(false);
  });

  it('returns false when sourceImageId is empty', () => {
    expect(isEvidenceDisplayable('VALID', true, null)).toBe(false);
    expect(isEvidenceDisplayable('VALID', true, '  ')).toBe(false);
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
