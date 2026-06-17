/**
 * v3.1.1 Epic 1 — Result mappers tests.
 */

import { describe, it, expect } from 'vitest';
import type {
  PositionSummary,
  PositionDetailResponse,
  EvidenceSummary,
  ReviewActionSummary,
} from '../src/api/types';
import {
  mapTraceabilityToVisible,
  mapPositionStatusToReviewStatus,
  mapPositionSummaryToResultSummary,
  mapPositionDetailToResultDetail,
  mapEvidenceToResultEvidence,
  mapReviewActionToHistoryItem,
} from '../src/features/results/mappers';
import { getSummaryString, getSummaryNumber } from '../src/features/results/mappers/detectedSummary';

const rcLegacy = (): PositionDetailResponse['run_context'] => ({
  job_id: null,
  result_context_source: 'legacy',
  resolved_job_id: null,
});

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
  it('maps reviewed + review_resolution image_mismatch -> IMAGE_MISMATCH', () => {
    expect(mapPositionStatusToReviewStatus('reviewed', false, 'image_mismatch')).toBe(
      'IMAGE_MISMATCH'
    );
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
  it('maps all fields and uses has_evidence as canonical (v3.2.5 Block 4)', () => {
    const p: PositionSummary = {
      id: 'pos-1',
      aisle_id: 'aisle-1',
      position_code: '',
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
      has_evidence: true,
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

  it('hasEvidence false when has_evidence is false (v3.2.5 Block 4)', () => {
    const p: PositionSummary = {
      id: 'pos-2',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'reviewed',
      confidence: 1,
      needs_review: false,
      primary_evidence_id: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      qty: 1,
      qtySource: 'detected',
      has_evidence: false,
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(false);
    expect(r.reviewStatus).toBe('CONFIRMED');
  });

  it('review_resolution image_mismatch maps list row to IMAGE_MISMATCH', () => {
    const p: PositionSummary = {
      id: 'pos-img',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'reviewed',
      confidence: 0.9,
      needs_review: false,
      primary_evidence_id: 'ev-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      sku: 'SKU-X',
      detected_quantity: 4,
      corrected_quantity: null,
      qty: 4,
      qtySource: 'detected',
      has_evidence: true,
      review_resolution: 'image_mismatch',
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.reviewStatus).toBe('IMAGE_MISMATCH');
    expect(r.sku).toBe('SKU-X');
    expect(r.resolvedQty).toBe(4);
  });

  it('Sprint 2: prefers nested product/quantity/traceability blocks over divergent legacy flat fields', () => {
    const p: PositionSummary = {
      id: 'pos-s2-blocks',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.9,
      needs_review: false,
      primary_evidence_id: 'ev-legacy',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      sku: 'FLAT-SKU',
      detected_quantity: 1,
      corrected_quantity: null,
      qty: 1,
      qtySource: 'detected',
      qtyResolved: null,
      has_evidence: false,
      product: {
        sku: 'BLOCK-SKU',
        identity_source: 'primary_product',
      },
      quantity: {
        detected: 9,
        final: 9,
        source: 'merge_inferred',
        resolved: true,
      },
      traceability: {
        status: 'missing',
        has_evidence: true,
        primary_evidence_id: 'ev-block',
      },
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.sku).toBe('BLOCK-SKU');
    expect(r.detectedQty).toBe(9);
    expect(r.qtySource).toBe('merge_inferred');
    expect(r.qtyResolved).toBe(true);
    expect(r.resolvedQty).toBe(9);
    expect(r.traceabilityStatus).toBe('MISSING');
    expect(r.hasEvidence).toBe(true);
  });

  it('preserves qtySource = consolidated (Phase 5 Block 1) and keeps visible qty rule', () => {
    const p: PositionSummary = {
      id: 'pos-consolidated',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.9,
      needs_review: false,
      primary_evidence_id: 'ev-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      detected_quantity: 7,
      corrected_quantity: null,
      qty: 7,
      qtySource: 'consolidated',
      qtyResolved: true,
      has_evidence: true,
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.qtySource).toBe('consolidated');
    expect(r.qtyResolved).toBe(true);
    // Display rule remains: corrected_quantity ?? qty.
    expect(r.resolvedQty).toBe(7);
  });

  it('uses has_evidence true from API and produces hasEvidence true', () => {
    const p: PositionSummary = {
      id: 'pos-3',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.8,
      needs_review: true,
      primary_evidence_id: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      qty: 1,
      qtySource: 'detected',
      has_evidence: true,
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(true);
  });

  it('Case 4 — fallback when has_evidence omitted (transitional payload): uses primary_evidence_id', () => {
    const p = {
      id: 'pos-transitional',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.8,
      needs_review: false,
      primary_evidence_id: 'ev-99',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      qty: 1,
      qtySource: 'detected',
    } as PositionSummary;
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(true);
  });
});

describe('mapEvidenceToResultEvidence', () => {
  it('maps primary evidence with role PRIMARY', () => {
    const r = mapEvidenceToResultEvidence({
      id: 'ev-1',
      entity_type: 'PALLET',
      entity_id: 'e1',
      type: 'position_crop',
      storage_path: '/path',
      source_asset_id: 'asset-1',
      is_primary: true,
    });
    expect(r.id).toBe('ev-1');
    expect(r.role).toBe('PRIMARY');
    expect(r.sourceImageId).toBe('asset-1');
    expect(r.sourceFileName).toBeNull();
    expect(r.imageUrl).toBeNull();
  });

  it('maps supporting evidence with role SUPPORTING', () => {
    const r = mapEvidenceToResultEvidence({
      id: 'ev-2',
      entity_type: 'PALLET',
      entity_id: 'e1',
      type: 'product_crop',
      storage_path: '/path2',
      is_primary: false,
    });
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
      position_code: '',
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
        source_image_id: 'img-1',
        source_image_original_filename: 'photo.jpg',
        traceability_status: 'valid',
        has_evidence: true,
      },
      technical_snapshot: {
        entity_uid: 'job_E1',
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
      run_context: rcLegacy(),
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

  it('storageJobId is only position.job_id; run_context ids are separate (never mixed for review writes)', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-job',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.9,
        needs_review: true,
        primary_evidence_id: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        job_id: 'storage-run-1',
        qty: 1,
        qtySource: 'detected',
        has_evidence: false,
      },
      evidences: [],
      review_actions: [],
      run_context: {
        job_id: 'slice-view',
        result_context_source: 'explicit',
        resolved_job_id: 'resolved-view',
      },
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.storageJobId).toBe('storage-run-1');
    expect(r.runContextJobId).toBe('slice-view');
    expect(r.runContextResolvedJobId).toBe('resolved-view');
  });

  it('legacy row: storageJobId null even when run_context carries a slice job_id', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-legacy',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.9,
        needs_review: true,
        primary_evidence_id: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        qty: 1,
        qtySource: 'detected',
        has_evidence: false,
      },
      evidences: [],
      review_actions: [],
      run_context: {
        job_id: 'only-in-context',
        result_context_source: 'legacy',
        resolved_job_id: null,
      },
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.storageJobId).toBeNull();
    expect(r.runContextJobId).toBe('only-in-context');
  });

  it('Case 1 — uses typed source_image fields as canonical when present (v3.2.5 Block 3)', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-canonical',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.9,
        needs_review: true,
        primary_evidence_id: 'ev-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        sku: 'SKU-A',
        detected_quantity: 5,
        corrected_quantity: null,
        qty: 5,
        qtySource: 'detected',
        qtyResolved: true,
        source_image_id: 'canonical-id',
        source_image_original_filename: 'canonical.jpg',
        traceability_status: 'valid',
        has_evidence: true,
      },
      technical_snapshot: {
        entity_uid: 'job_override',
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.sourceImageId).toBe('canonical-id');
    expect(r.sourceFileName).toBe('canonical.jpg');
    expect(r.technicalMetadata?.entityId).toBe('job_override');
  });

  it('Case 2 — typed source image fields are required when technical snapshot is separate', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-fallback',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.8,
        needs_review: false,
        primary_evidence_id: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        sku: 'SKU-B',
        detected_quantity: 2,
        corrected_quantity: null,
        qty: 2,
        qtySource: 'detected',
        qtyResolved: null,
        source_image_id: null,
        source_image_original_filename: null,
        traceability_status: null,
        has_evidence: false,
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.sourceImageId).toBeNull();
    expect(r.sourceFileName).toBeNull();
  });

  it('Case 2b — technical_snapshot is preferred for technical metadata when present', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-technical-snapshot',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.8,
        needs_review: false,
        primary_evidence_id: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        sku: 'SKU-B',
        detected_quantity: 2,
        corrected_quantity: null,
        qty: 2,
        qtySource: 'detected',
        qtyResolved: null,
        source_image_id: null,
        source_image_original_filename: null,
        traceability_status: null,
        has_evidence: false,
      },
      technical_snapshot: {
        entity_uid: 'job_new',
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.technicalMetadata?.entityId).toBe('job_new');
  });

  it('Case 3 — neither typed nor summary: source fields null, no crash (v3.2.5 Block 3)', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-no-source',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.5,
        needs_review: true,
        primary_evidence_id: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        sku: null,
        detected_quantity: 0,
        corrected_quantity: null,
        qty: 0,
        qtySource: 'detected',
        qtyResolved: false,
        source_image_id: null,
        source_image_original_filename: null,
        traceability_status: null,
        has_evidence: false,
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.sourceImageId).toBeNull();
    expect(r.sourceFileName).toBeNull();
    expect(r.id).toBe('pos-no-source');
  });

  it('handles empty evidences and review_actions', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-2',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'reviewed',
        confidence: 1,
        needs_review: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        qty: 0,
        qtySource: 'detected',
        has_evidence: false,
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.evidence).toEqual([]);
    expect(r.reviewHistory).toEqual([]);
    expect(r.correctedQty).toBeNull();
  });

  it('Case 4 — qtySource omitted (historical payload): fallback to detected', () => {
    const data = {
      position: {
        id: 'pos-historical',
        aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
        confidence: 0.8,
        needs_review: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        qty: 3,
        detected_quantity: 3,
        corrected_quantity: null,
        sku: 'SKU-Old',
        source_image_id: null,
        source_image_original_filename: null,
        traceability_status: null,
        has_evidence: false,
      },
      evidences: [] as EvidenceSummary[],
      review_actions: [] as ReviewActionSummary[],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data as PositionDetailResponse);
    expect(r.qtySource).toBe('detected');
    expect(r.resolvedQty).toBe(3);
  });

  it('Case 5 — has_evidence explicitly false is not overridden by primary_evidence_id (canonical wins)', () => {
    const p: PositionSummary = {
      id: 'pos-canonical-false',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.9,
      needs_review: true,
      primary_evidence_id: 'ev-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      qty: 1,
      qtySource: 'detected',
      has_evidence: false,
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasEvidence).toBe(false);
  });

  it('Phase 4.2: hasValidEvidence follows traceability.has_valid_evidence', () => {
    const p: PositionSummary = {
      id: 'pos-hve',
      aisle_id: 'aisle-1',
      position_code: '',
      status: 'detected',
      confidence: 0.9,
      needs_review: true,
      primary_evidence_id: 'ev-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      qty: 1,
      qtySource: 'detected',
      has_evidence: true,
      traceability: {
        status: 'invalid',
        source_image_id: 'asset-bad',
        has_evidence: true,
        has_valid_evidence: false,
      },
    };
    const r = mapPositionSummaryToResultSummary(p);
    expect(r.hasValidEvidence).toBe(false);
    expect(r.traceabilityStatus).toBe('INVALID');
  });
});

describe('mapPositionDetailToResultDetail Phase 4.2', () => {
  it('invalid traceability keeps sourceImageId but hasValidEvidence false', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-inv',
        aisle_id: 'aisle-1',
        position_code: '',
        status: 'detected',
        confidence: 0.9,
        needs_review: true,
        primary_evidence_id: 'ev-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        qty: 1,
        qtySource: 'detected',
        has_evidence: true,
        traceability: {
          status: 'invalid',
          source_image_id: 'asset-bad',
          has_evidence: true,
          has_valid_evidence: false,
          traceability_warning: 'Returned image ID was not part of the final provider payload.',
        },
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };
    const r = mapPositionDetailToResultDetail(data);
    expect(r.sourceImageId).toBe('asset-bad');
    expect(r.hasValidEvidence).toBe(false);
    expect(r.traceabilityWarning).toContain('final provider payload');
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
