/**
 * Phase 4.8 — structural evidence contract tests (types, mapper, eligibility).
 */

import { describe, it, expect } from 'vitest';
import type {
  JobTraceabilityResponse,
  PositionDetailResponse,
  ResultEvidenceViewResponse,
} from '../src/api/types';
import {
  mapPositionDetailToResultDetail,
  mapResultEvidenceViewResponse,
  mapTraceabilityToVisible,
} from '../src/features/results/mappers';
import {
  isEvidenceDisplayable,
  isLegacyEvidenceDisplayable,
} from '../src/features/results/utils/evidenceEligibility';

const rcLegacy = (): PositionDetailResponse['run_context'] => ({
  job_id: null,
  result_context_source: 'legacy',
  resolved_job_id: null,
});

function structuralEvidence(
  overrides: Partial<ResultEvidenceViewResponse> = {}
): ResultEvidenceViewResponse {
  return {
    displayable: true,
    traceability_status: 'valid',
    source_kind: 'structural_result_evidence',
    source_image_id: 'asset-structural',
    source_asset_id: 'asset-structural',
    provider: 'gemini',
    model_name: 'gemini-2.0',
    resolved_manifest_entry_id: 'manifest-resolved-1',
    raw_manifest_entry_id: 'manifest-raw-1',
    ...overrides,
  };
}

describe('Phase 4.8 API contract shapes', () => {
  it('JobTraceabilityResponse includes entities with nested evidence', () => {
    const payload: JobTraceabilityResponse = {
      job_id: 'job-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      traceability: {
        status: 'published',
        artifact: {
          kind: 'hybrid_report',
          published: true,
          required: false,
          status: 'available',
        },
        summary: {
          total_evidence_rows: 1,
          valid: 1,
          invalid: 0,
          missing: 0,
          unvalidated: 0,
          displayable: 1,
          not_displayable: 0,
          reference_rejected: 0,
          unknown_identifier: 0,
          conflicting_identifier: 0,
          manifest_unavailable: 0,
          manifest_invalid: 0,
          artifact_published: 1,
        },
      },
      entities: [
        {
          position_id: 'pos-1',
          entity_uid: 'job-1_E1',
          evidence: structuralEvidence({ displayable: false, traceability_status: 'invalid' }),
        },
      ],
    };

    expect(payload.entities[0]?.evidence.displayable).toBe(false);
    expect(payload.traceability.artifact?.status).toBe('available');
  });
});

describe('mapResultEvidenceViewResponse', () => {
  it('maps snake_case API fields to camelCase visible model', () => {
    const view = mapResultEvidenceViewResponse(structuralEvidence());
    expect(view.displayable).toBe(true);
    expect(view.traceabilityStatus).toBe('valid');
    expect(view.sourceImageId).toBe('asset-structural');
    expect(view.provider).toBe('gemini');
    expect(view.resolvedManifestEntryId).toBe('manifest-resolved-1');
    expect(view.sourceKind).toBe('structural_result_evidence');
  });
});

describe('mapPositionDetailToResultDetail Phase 4.8', () => {
  it('maps evidence field to evidenceView and syncs traceability from structural contract', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-1',
        aisle_id: 'aisle-1',
        position_code: 'P1',
        status: 'detected',
        confidence: 0.9,
        needs_review: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        qty: 1,
        qtySource: 'detected',
        has_evidence: true,
        traceability: {
          status: 'valid',
          has_evidence: true,
          has_valid_evidence: true,
          source_image_id: 'legacy-asset',
        },
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
      evidence: structuralEvidence({
        displayable: false,
        traceability_status: 'invalid',
        traceability_warning: 'Manifest entry rejected.',
        source_image_id: 'structural-asset',
      }),
    };

    const result = mapPositionDetailToResultDetail(data);
    expect(result.evidenceView?.displayable).toBe(false);
    expect(result.evidenceView?.traceabilityStatus).toBe('invalid');
    expect(result.traceabilityStatus).toBe('INVALID');
    expect(result.hasValidEvidence).toBe(false);
    expect(result.sourceImageId).toBe('structural-asset');
    expect(result.traceabilityWarning).toBe('Manifest entry rejected.');
  });

  it('leaves evidenceView null when API omits structural evidence', () => {
    const data: PositionDetailResponse = {
      position: {
        id: 'pos-legacy',
        aisle_id: 'aisle-1',
        position_code: 'P1',
        status: 'detected',
        confidence: 0.9,
        needs_review: false,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
        qty: 1,
        qtySource: 'detected',
        has_evidence: true,
        traceability: {
          status: 'valid',
          has_evidence: true,
          has_valid_evidence: true,
          source_image_id: 'asset-legacy',
        },
      },
      evidences: [],
      review_actions: [],
      run_context: rcLegacy(),
    };

    const result = mapPositionDetailToResultDetail(data);
    expect(result.evidenceView).toBeNull();
    expect(result.hasValidEvidence).toBe(true);
  });
});

describe('isEvidenceDisplayable Phase 4.8', () => {
  it('uses evidenceView.displayable as authoritative when structural view is present', () => {
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
        sourceImageId: 'asset-1',
      })
    ).toBe(true);
  });

  it('falls back to legacy gate only when explicitly allowed', () => {
    expect(isEvidenceDisplayable('VALID', true, 'asset-1')).toBe(false);
    expect(isEvidenceDisplayable('VALID', true, 'asset-1', null)).toBe(false);
    expect(
      isEvidenceDisplayable('VALID', true, 'asset-1', null, { allowLegacyEvidenceFallback: true })
    ).toBe(true);
    expect(
      isEvidenceDisplayable('VALID', false, 'asset-1', null, { allowLegacyEvidenceFallback: true })
    ).toBe(false);
  });

  it('legacy_unavailable maps to UNVALIDATED for chip display', () => {
    expect(mapTraceabilityToVisible('legacy_unavailable')).toBe('UNVALIDATED');
    expect(mapTraceabilityToVisible('artifact_unavailable')).toBe('UNVALIDATED');
  });
});

describe('isLegacyEvidenceDisplayable', () => {
  it('mirrors Phase 4.2 legacy rules', () => {
    expect(isLegacyEvidenceDisplayable('VALID', true, 'asset-1')).toBe(true);
    expect(isLegacyEvidenceDisplayable('VALID', true, null)).toBe(false);
  });
});
