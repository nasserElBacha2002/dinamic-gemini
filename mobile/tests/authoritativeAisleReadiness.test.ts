import { evaluateLocalAuthoritativeAisleReadiness } from '../src/features/authoritativeAisleFinalization/authoritativeAisleReadiness';

describe('evaluateLocalAuthoritativeAisleReadiness', () => {
  it('is READY when all uploaded photos are synced and applied', () => {
    const result = evaluateLocalAuthoritativeAisleReadiness({
      enabled: true,
      photos: [
        { id: 'p1', upload_status: 'uploaded', backend_asset_id: 'a1' },
        { id: 'p2', upload_status: 'excluded', backend_asset_id: null },
      ],
      confirmed: [
        { capture_photo_id: 'p1', sync_status: 'SYNCED', applied_at: '2026-07-01T00:00:00Z' },
      ],
    });
    expect(result.status).toBe('READY');
    expect(result.appliedImages).toBe(1);
    expect(result.excludedImages).toBe(1);
  });

  it('disables button path when pending sync', () => {
    const result = evaluateLocalAuthoritativeAisleReadiness({
      enabled: true,
      photos: [{ id: 'p1', upload_status: 'uploaded', backend_asset_id: 'a1' }],
      confirmed: [{ capture_photo_id: 'p1', sync_status: 'PENDING', applied_at: null }],
    });
    expect(result.status).toBe('NOT_READY');
    expect(result.reasons).toContain('PENDING_AUTHORITATIVE_SYNC');
  });

  it('blocks when feature disabled', () => {
    const result = evaluateLocalAuthoritativeAisleReadiness({
      enabled: false,
      photos: [],
      confirmed: [],
    });
    expect(result.status).toBe('BLOCKED');
    expect(result.reasons).toContain('FEATURE_DISABLED');
  });
});
