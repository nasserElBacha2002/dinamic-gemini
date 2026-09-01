import {
  classifySessionsForAisle,
  listSessionsForAisle,
  workForAisle,
} from '../src/features/capture/localAisleWork';
import type { CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

function session(overrides: Partial<CaptureSessionRow>): CaptureSessionRow {
  const now = '2026-01-01T00:00:00.000Z';
  return {
    id: 's1',
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_id: 'aisle-1',
    aisle_name: 'A1',
    status: 'local_completed',
    started_at: now,
    finished_at: now,
    initial_asset_id: null,
    initial_date_added: null,
    initial_date_modified: null,
    initial_display_name: null,
    initial_size: null,
    initial_bucket_id: null,
    scan_cursor_date_added: EMPTY_CURSOR.dateAdded,
    scan_cursor_asset_id: EMPTY_CURSOR.assetId,
    last_valid_cursor_date_added: EMPTY_CURSOR.dateAdded,
    last_valid_cursor_asset_id: EMPTY_CURSOR.assetId,
    upload_batch_id: 'b1',
    upload_status: 'idle',
    processing_status: 'idle',
    backend_job_id: null,
    upload_started_at: null,
    upload_completed_at: null,
    processing_started_at: null,
    processing_finished_at: null,
    last_upload_error: null,
    last_processing_error: null,
    preparation_processing_mode: 'CODE_SCAN',
    backend_ordered_capture_session_id: null,
    process_attempt_id: null,
    process_idempotency_key: null,
    process_requested_at: null,
    process_confirmed_at: null,
    last_recovery_check_at: null,
    capture_frozen_at: now,
    capture_frozen_photo_count: 2,
    capture_freeze_generation: 1,
    active_freeze_id: 'f1',
    upload_policy: 'MANUAL',
    created_at: now,
    updated_at: now,
    ...overrides,
  } as CaptureSessionRow;
}

describe('localAisleWork multi-session', () => {
  it('lists all sessions for an aisle without dropping older ones', () => {
    const sessions = [
      session({ id: 'newer', updated_at: '2026-02-01T00:00:00.000Z', status: 'local_completed' }),
      session({ id: 'older', updated_at: '2026-01-01T00:00:00.000Z', status: 'local_completed' }),
      session({ id: 'other', aisle_id: 'aisle-2', status: 'paused' }),
    ];
    const forAisle = listSessionsForAisle(sessions, 'aisle-1');
    expect(forAisle.map((s) => s.id)).toEqual(['newer', 'older']);
    const classified = classifySessionsForAisle(sessions, 'aisle-1', []);
    expect(classified).toHaveLength(2);
    expect(classified.every((w) => w.kind === 'local_completed')).toBe(true);
  });

  it('prefers exclusive capture as primary work over newer local_completed', () => {
    const sessions = [
      session({
        id: 'saved',
        updated_at: '2026-03-01T00:00:00.000Z',
        status: 'local_completed',
      }),
      session({
        id: 'active',
        updated_at: '2026-02-01T00:00:00.000Z',
        status: 'active',
      }),
    ];
    const work = workForAisle(sessions, 'aisle-1', []);
    expect(work?.sessionId).toBe('active');
    expect(work?.kind).toBe('capture_active');
  });

  it('exposes shortId and updatedAt for UI identification', () => {
    const work = workForAisle(
      [session({ id: 'abcdefgh-ijkl', updated_at: '2026-01-15T12:00:00.000Z' })],
      'aisle-1',
      [],
    );
    expect(work?.shortId).toBe('abcdefgh');
    expect(work?.updatedAt).toBe('2026-01-15T12:00:00.000Z');
    expect(work?.label).toMatch(/localmente/i);
  });

  it('maps legacy upload sessions to local_completed when server upload is off', () => {
    const work = workForAisle(
      [session({ status: 'uploading' })],
      'aisle-1',
      [{ sessionId: 's1', pending: 3, uploaded: 0, totalStable: 5, inventoryName: 'Inv', aisleName: 'A1', uploading: 0, retryable: 0, permanent: 0, excluded: 0 }],
      { serverUploadEnabled: false },
    );
    expect(work?.kind).toBe('local_completed');
    expect(work?.pendingUploads).toBe(0);
    expect(work?.label).toMatch(/exportable offline/i);
  });
});
