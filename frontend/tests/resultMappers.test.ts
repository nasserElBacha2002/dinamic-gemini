/**
 * v3.1.1 Epic 1 — Result mappers tests.
 */

import { describe, it, expect } from 'vitest';
import type { PositionSummary, PositionDetailResponse } from '../src/api/types';
import {
  mapTraceabilityToVisible,
  mapPositionStatusToReviewStatus,
  mapPositionSummaryToResultSummary,
  mapPositionDetailToResultDetail,
  mapEvidenceToResultEvidence,
  mapReviewActionToHistoryItem,
} from '../src/features/results/mappers';
import { getSummaryString, getSummaryNumber } from '../src/features/results/mappers/detectedSummary';

describe('mapTraceabilityToVisible', () => {
  it('maps valid -> VALID', () => {
    expect(mapTraceabilityToVisible('valid')).toBe('VALID');
  });
  it('maps missing -> MISSING', () => {
    expect(mapTraceabilityToVisible('missing')).toBe('MISSING');
  });
  it('maps invalid -> INVALID', () => {
    expect(mapTraceabilityToVisible('invalid')).toBe('INVALID');
  });
  it('maps unvalidated -> UNVALIDATED', () => {
    expect(mapTraceabilityToVisible('unvalidated')).toBe('UNVALIDATED');
  });
  it('defaults null/empty/unknown to UNVALIDATED', () => {
    expect(mapTraceabilityToVisible(null)).toBe('UNVALIDATED');
    expect(mapTraceabilityToVisible('')).toBe('UNVALIDATED');
    expect(mapTraceabilityToVisible('unknown')).toBe('UNVALIDATED');
  });
});

describe('mapPositionStatusToReviewStatus', () => {
  it('maps detected + needs_review -> NEEDS_REVIEW', () => {
    expect(mapPositionStatusToReviewStatus('detected', true)).toBe('NEEDS_REVIEW');
  });
  it('maps detected + !needs_review -> DETECTED', () => {
    expect(mapPositionStatusToReviewStatus('detected', false)).toBe('DETECTED');
  });
  it('maps reviewed -> CONFIRMED', () => {
    expect(mapPositionStatusToReviewStatus('reviewed', false)).toBe('CONFIRMED');
  });
  it('maps corrected -> CONFIRMED', () => {
    expect(mapPositionStatusToReviewStatus('corrected', false)).toBe('CONFIRMED');
  });
  it('maps deleted -> INVALID', () => {
    expect(mapPositionStatusToReviewStatus('deleted', false)).toBe('INVALID');
  });
  it('accepts null/undefined status and treats as unknown -> DETECTED', () => {
    expect(mapPositionStatusToReviewStatus(null, false)).toBe('DETECTED');
    expect(mapPositionStatusToReviewStatus(undefined, false)).toBe('DETECTED');
  });
  it('accepts empty string status -> DETECTED', () => {
    expect(mapPositionStatusToReviewStatus('', false)).toBe('DETECTED');
  });
});

describe('mapPositionSummaryToResultSummary', () => {
  it('maps all fields and sets hasEvidence from primary_evidence_id', () => {
    const p: PositionSummary = {
      id: 'pos-1',
      aisle_id: 'aisle-1',
      status: 'detected',
      confidence: 0.92,
      needs_review: true,
      primary_evidence_id: 'ev-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      sku: 'SKU-X',
      detected_quantity: 10,
      corrected_quantity: null,
      qty: 1,
      qtySource: 'inferred',
      qtyResolved: true,
      traceability_status: 'valid',
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.id).toBe('pos-1');
    expect(r.sku).toBe('SKU-X');
    expect(r.detectedQty).toBe(10);
    expect(r.correctedQty).toBeNull();
    // Display rule: corrected_quantity ?? qty; here qty=1 and no correction.
    expect(r.resolvedQty).toBe(1);
    expect(r.confidence).toBe(0.92);
    expect(r.reviewStatus).toBe('NEEDS_REVIEW');
    expect(r.traceabilityStatus).toBe('VALID');
    expect(r.needsReview).toBe(true);
    expect(r.updatedAt).toBe('2024-01-02T00:00:00Z');
    expect(r.hasEvidence).toBe(true);
  });

  it('hasEvidence false when primary_evidence_id is null', () => {
    const p: PositionSummary = {
      id: 'pos-2',
      aisle_id: 'aisle-1',
      status: 'reviewed',
      confidence: 1,
      needs_review: false,
      primary_evidence_id: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(false);
    expect(r.reviewStatus).toBe('CONFIRMED');
  });

  it('prefers API has_evidence when present (Epic 2)', () => {
    const p: PositionSummary = {
      id: 'pos-3',
      aisle_id: 'aisle-1',
      status: 'detected',
      confidence: 0.8,
      needs_review: true,
      primary_evidence_id: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      has_evidence: true,
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(true);
  });
});

describe('mapEvidenceToResultEvidence', () => {
  it('maps primary evidence with role PRIMARY', () => {
    const r = mapEvidenceToResultEvidence(
      {
        id: 'ev-1',
        entity_type: 'PALLET',
        entity_id: 'e1',
        type: 'position_crop',
        storage_path: '/path',
        source_asset_id: 'asset-1',
        is_primary: true,
      },
      0
    );
    expect(r.id).toBe('ev-1');
    expect(r.role).toBe('PRIMARY');
    expect(r.sourceImageId).toBe('asset-1');
    expect(r.sourceFileName).toBeNull();
    expect(r.imageUrl).toBeNull();
  });

  it('maps supporting evidence with role SUPPORTING', () => {
    const r = mapEvidenceToResultEvidence(
      {
        id: 'ev-2',
        entity_type: 'PALLET',
        entity_id: 'e1',
        type: 'product_crop',
        storage_path: '/path2',
        is_primary: false,
      },
      1
    );
    expect(r.role).toBe('SUPPORTING');
    expect(r.sourceImageId).toBeNull();
  });
});

describe('mapReviewActionToHistoryItem', () => {
  it('maps action type and dates', () => {
    const a = mapReviewActionToHistoryItem({
      id: 'ra-1',
      position_id: 'pos-1',
      action_type: 'confirm',
      before_json: {},
      after_json: {},
      created_at: '2024-01-03T12:00:00Z',
      user_id: 'user-1',
      comment: 'Confirmed',
    });
    expect(a.id).toBe('ra-1');
    expect(a.action).toBe('confirm');
    expect(a.createdAt).toBe('2024-01-03T12:00:00Z');
    expect(a.userName).toBe('user-1');
    expect(a.notes).toBe('Confirmed');
  });
});

describe('mapPositionDetailToResultDetail', () => {
  it('maps full detail with evidences and review history', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-1',
        aisle_id: 'aisle-1',
        status: 'detected',
        confidence: 0.9,
        needs_review: true,
        primary_evidence_id: 'ev-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        sku: 'SKU-A',
        detected_quantity: 5,
        corrected_quantity: 6,
        qty: 1,
        qtySource: 'inferred',
        qtyResolved: true,
        detected_summary_json: {
          entity_uid: 'job_E1',
          source_image_id: 'img-1',
          source_image_original_filename: 'photo.jpg',
        },
        source_image_id: 'img-1',
        traceability_status: 'valid',
      },
      evidences: [
        {
          id: 'ev-1',
          entity_type: 'PALLET',
          entity_id: 'e1',
          type: 'position_crop',
          storage_path: '/path',
          is_primary: true,
        },
      ],
      review_actions: [
        {
          id: 'ra-1',
          position_id: 'pos-1',
          action_type: 'confirm',
          before_json: {},
          after_json: {},
          created_at: '2024-01-03T00:00:00Z',
        },
      ],
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.id).toBe('pos-1');
    expect(r.sku).toBe('SKU-A');
    expect(r.detectedQty).toBe(5);
    expect(r.correctedQty).toBe(6);
    // Display rule: corrected_quantity wins over qty.
    expect(r.resolvedQty).toBe(6);
    expect(r.reviewStatus).toBe('NEEDS_REVIEW');
    expect(r.traceabilityStatus).toBe('VALID');
    expect(r.sourceImageId).toBe('img-1');
    expect(r.sourceFileName).toBe('photo.jpg');
    expect(r.evidence).toHaveLength(1);
    expect(r.evidence[0].role).toBe('PRIMARY');
    expect(r.reviewHistory).toHaveLength(1);
    expect(r.reviewHistory[0].action).toBe('confirm');
    expect(r.technicalMetadata?.entityId).toBe('job_E1');
    expect(r.technicalMetadata?.primaryEvidenceId).toBe('ev-1');
  });

  it('handles empty evidences and review_actions', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-2',
        aisle_id: 'aisle-1',
        status: 'reviewed',
        confidence: 1,
        needs_review: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      evidences: [],
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.evidence).toEqual([]);
    expect(r.reviewHistory).toEqual([]);
    expect(r.correctedQty).toBeNull();
  });
});

describe('detectedSummary helpers', () => {
  it('getSummaryString returns string for present key', () => {
    expect(getSummaryString({ a: 'x' }, 'a')).toBe('x');
    expect(getSummaryString({ entity_uid: 'job_E1' }, 'entity_uid')).toBe('job_E1');
  });
  it('getSummaryString returns null for missing or non-string', () => {
    expect(getSummaryString({}, 'a')).toBeNull();
    expect(getSummaryString(null, 'a')).toBeNull();
    expect(getSummaryString(undefined, 'a')).toBeNull();
    expect(getSummaryString({ a: '' }, 'a')).toBeNull();
  });
  it('getSummaryNumber returns number for numeric value', () => {
    expect(getSummaryNumber({ n: 42 }, 'n')).toBe(42);
    expect(getSummaryNumber({ n: '99' }, 'n')).toBe(99);
  });
  it('getSummaryNumber returns null for missing or non-numeric', () => {
    expect(getSummaryNumber({}, 'n')).toBeNull();
    expect(getSummaryNumber({ n: 'x' }, 'n')).toBeNull();
  });
});
