import { describe, it, expect } from 'vitest';
import {
  alignInventoryApiStatusToTarget,
  alignAisleApiStatusToTarget,
  alignPositionToResultReviewTarget,
  deriveQualityAlignmentSignals,
  LOW_CONFIDENCE_THRESHOLD,
} from '../src/types/statusAlignment';

describe('alignInventoryApiStatusToTarget', () => {
  it('maps exact plan-aligned values', () => {
    expect(alignInventoryApiStatusToTarget('draft')).toMatchObject({
      raw: 'draft',
      target: 'draft',
      isApproximate: false,
    });
    expect(alignInventoryApiStatusToTarget('completed')).toMatchObject({
      target: 'completed',
      isApproximate: false,
    });
  });
  it('maps processing lifecycle to in_progress (approximate)', () => {
    expect(alignInventoryApiStatusToTarget('processing')).toMatchObject({
      target: 'in_progress',
      isApproximate: true,
    });
    expect(alignInventoryApiStatusToTarget('in_review')).toMatchObject({
      target: 'in_progress',
      isApproximate: true,
    });
  });
  it('leaves failed unmapped (no plan counterpart)', () => {
    expect(alignInventoryApiStatusToTarget('failed')).toMatchObject({
      raw: 'failed',
      target: null,
      isApproximate: false,
    });
  });
});

describe('alignAisleApiStatusToTarget', () => {
  it('maps assets_uploaded and processed exactly', () => {
    expect(alignAisleApiStatusToTarget('assets_uploaded')).toMatchObject({
      target: 'assets_uploaded',
      isApproximate: false,
    });
    expect(alignAisleApiStatusToTarget('processed')).toMatchObject({
      target: 'processed',
      isApproximate: false,
    });
  });
  it('maps failed to error (approximate label)', () => {
    expect(alignAisleApiStatusToTarget('failed')).toMatchObject({
      target: 'error',
      isApproximate: true,
    });
  });
  it('maps created to empty (approximate)', () => {
    expect(alignAisleApiStatusToTarget('created')).toMatchObject({
      target: 'empty',
      isApproximate: true,
    });
  });
});

describe('alignPositionToResultReviewTarget', () => {
  it('maps detected + needs_review to pending_review', () => {
    expect(alignPositionToResultReviewTarget('detected', true)).toMatchObject({
      target: 'pending_review',
      resolutionKind: 'pending_review',
      isApproximate: false,
    });
  });
  it('maps detected + !needs_review to plan confirmed with auto_accepted resolution', () => {
    const r = alignPositionToResultReviewTarget('detected', false);
    expect(r.target).toBe('confirmed');
    expect(r.resolutionKind).toBe('auto_accepted');
    expect(r.isApproximate).toBe(true);
  });
  it('maps reviewed to plan confirmed with human_confirmed resolution', () => {
    const r = alignPositionToResultReviewTarget('reviewed', false);
    expect(r.target).toBe('confirmed');
    expect(r.resolutionKind).toBe('human_confirmed');
    expect(r.isApproximate).toBe(false);
  });
  it('maps reviewed + image_mismatch to its own plan target (not unknown)', () => {
    expect(
      alignPositionToResultReviewTarget('reviewed', false, 'image_mismatch')
    ).toMatchObject({
      target: 'image_mismatch',
      resolutionKind: 'image_mismatch',
      isApproximate: false,
    });
  });
  it('maps corrected and deleted', () => {
    expect(alignPositionToResultReviewTarget('corrected', false)).toMatchObject({
      target: 'corrected',
      resolutionKind: 'corrected',
    });
    expect(alignPositionToResultReviewTarget('deleted', false)).toMatchObject({
      target: 'deleted',
      resolutionKind: 'deleted',
    });
  });
});

describe('deriveQualityAlignmentSignals', () => {
  it('classifies traceability into plan buckets', () => {
    expect(
      deriveQualityAlignmentSignals('valid', 0.9).traceabilityTarget
    ).toBe('valid_traceability');
    expect(
      deriveQualityAlignmentSignals('invalid', 0.9).traceabilityTarget
    ).toBe('invalid_traceability');
    expect(
      deriveQualityAlignmentSignals('missing', 0.9).traceabilityTarget
    ).toBe('invalid_traceability');
    expect(deriveQualityAlignmentSignals('unvalidated', 0.9).traceabilityTarget).toBeNull();
  });
  it('flags low confidence independently', () => {
    expect(deriveQualityAlignmentSignals('valid', 0.2).lowConfidence).toBe(true);
    expect(deriveQualityAlignmentSignals('valid', 0.9).lowConfidence).toBe(false);
    expect(
      deriveQualityAlignmentSignals('valid', 0.9, {
        lowConfidenceThreshold: LOW_CONFIDENCE_THRESHOLD,
      }).lowConfidence
    ).toBe(false);
  });
});
