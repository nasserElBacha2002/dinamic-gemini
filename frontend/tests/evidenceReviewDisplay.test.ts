import { describe, it, expect } from 'vitest';
import {
  getResultReviewStatusForDisplay,
  getReviewStatusLabelForDisplay,
  hasImageMismatchEvidenceIssue,
  reviewStatusToBadgeSemanticForDisplay,
} from '../src/features/results/utils/evidenceReviewDisplay';
import { mapPositionSummaryToResultSummary } from '../src/features/results/mappers/positionToResult';
import type { PositionSummary } from '../src/api/types/responses';

describe('evidenceReviewDisplay', () => {
  it('hasImageMismatchEvidenceIssue is true only for IMAGE_MISMATCH', () => {
    expect(hasImageMismatchEvidenceIssue('IMAGE_MISMATCH')).toBe(true);
    expect(hasImageMismatchEvidenceIssue('CONFIRMED')).toBe(false);
  });

  it('maps IMAGE_MISMATCH review display to CONFIRMED semantics', () => {
    expect(getResultReviewStatusForDisplay('IMAGE_MISMATCH')).toBe('CONFIRMED');
    expect(reviewStatusToBadgeSemanticForDisplay('IMAGE_MISMATCH')).toBe('success');
  });

  it('review label for image mismatch is not an evidence-mismatch phrase in review column', () => {
    const label = getReviewStatusLabelForDisplay('IMAGE_MISMATCH');
    expect(label.toLowerCase()).not.toMatch(/imagen no coincide|evidencia incorrecta|image mismatch/);
    expect(label).toMatch(/confirmado|confirmed/i);
  });

  it('mapper keeps internal IMAGE_MISMATCH while display helpers separate evidence', () => {
    const p: PositionSummary = {
      id: 'pos-img',
      aisle_id: 'aisle-1',
      status: 'reviewed',
      position_code: 'P1',
      confidence: 0.9,
      needs_review: false,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      qty: 4,
      has_evidence: true,
      review_resolution: 'image_mismatch',
    };
    const row = mapPositionSummaryToResultSummary(p);
    expect(row.reviewStatus).toBe('IMAGE_MISMATCH');
    expect(hasImageMismatchEvidenceIssue(row.reviewStatus)).toBe(true);
    expect(getReviewStatusLabelForDisplay(row.reviewStatus)).toMatch(/confirmado|confirmed/i);
  });
});
