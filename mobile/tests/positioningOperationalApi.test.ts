import {
  buildProcessAisleRequestBody,
  sanitizeIdentificationModeSelection,
} from '../src/features/processing/processingMode';
import {
  PositioningOperationalApi,
} from '../src/features/positioning/positioningOperationalApi';

describe('positioningOperationalApi', () => {
  it('loads operational view and reprocess without forcing CODE_SCAN', async () => {
    const get = jest.fn().mockResolvedValue({
      processing_state: 'COMPLETED',
      active_job_id: null,
      result_job_id: 'job-1',
      reconciliation_status: 'COMPLETED',
      reconciliation_version: '1.0.0',
      total_results: 2,
      assigned_results: 1,
      unassigned_results: 1,
      manual_overrides_count: 0,
      detections_count: 1,
      recoverable: false,
      allowed_actions: {
        process: false,
        reprocess: true,
        recover: false,
        review: true,
        correct_position: false,
        restore_automatic: false,
        reconcile_only: true,
      },
      warnings: [],
      supported_reprocess_modes: ['REPROCESS_FULL_AISLE', 'RECONCILE_ONLY'],
      feature_flags: { POSITION_OPERATIONAL_UX_ENABLED: true },
    });
    const post = jest.fn().mockResolvedValue({
      mode: 'RECONCILE_ONLY',
      job_id: 'job-1',
      reconciliation_id: 'recon-1',
      detail: 'ok',
      manuals_preserved: true,
      manual_override_policy: 'PRESERVED',
      previous_manual_overrides_count: 0,
    });
    const api = new PositioningOperationalApi({ get, post } as never);
    const view = await api.getOperationalView('inv', 'aisle');
    expect(view.reconciliation_version).toBe('1.0.0');
    expect(view.allowed_actions.reprocess).toBe(true);

    await api.reprocess('inv', 'aisle', {
      idempotency_key: 'idem-12345678',
      reprocess_mode: 'RECONCILE_ONLY',
      expected_active_job_id: null,
      expected_result_job_id: 'job-1',
    });
    expect(post).toHaveBeenCalledWith(
      expect.stringContaining('/reprocess'),
      expect.objectContaining({
        identification_mode: null,
        expected_result_job_id: 'job-1',
      }),
    );
  });
});

describe('processingMode inherit (phase7 corrections)', () => {
  it('keeps inherit as omit identification_mode', () => {
    expect(sanitizeIdentificationModeSelection(null)).toBeNull();
    expect(buildProcessAisleRequestBody('k1', null)).toEqual({ idempotency_key: 'k1' });
  });
});
