import {
  canExportSession,
  isSessionExportableStatus,
} from '../src/features/localCsv/canExportSession';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';
import {
  mapLocalCsvExportError,
  userMessageForLocalCsvExportError,
} from '../src/features/localCsv/runLocalCsvExport';

function session(overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
  const now = '2026-01-01T00:00:00.000Z';
  return {
    id: 'session-1',
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
    capture_frozen_photo_count: 1,
    capture_freeze_generation: 1,
    active_freeze_id: 'freeze-1',
    upload_policy: 'MANUAL',
    created_at: now,
    updated_at: now,
    ...overrides,
  } as CaptureSessionRow;
}

function photo(overrides: Partial<CapturePhotoRow> = {}): CapturePhotoRow {
  return {
    id: 'session-1:1',
    capture_session_id: 'session-1',
    asset_id: '1',
    media_store_numeric_id: 1,
    uri: 'file://photo.jpg',
    display_name: 'photo.jpg',
    mime_type: 'image/jpeg',
    size: 10,
    width: 1,
    height: 1,
    date_added: 1,
    date_modified: 1,
    bucket_id: null,
    relative_path: null,
    status: 'stable',
    rejection_reason: null,
    stability_checks: 1,
    stability_attempts: 1,
    stability_error: null,
    last_stability_attempt_at: null,
    detected_at: '2026-01-01T00:00:00.000Z',
    stable_at: '2026-01-01T00:00:00.000Z',
    excluded_at: null,
    client_file_id: 'cf1',
    sequence_number: 1,
    backend_asset_id: null,
    upload_status: 'not_queued',
    upload_progress: 0,
    upload_attempts: 0,
    upload_batch_id: null,
    last_upload_error_code: null,
    last_upload_error_message: null,
    last_upload_attempt_at: null,
    next_retry_at: null,
    uploaded_at: null,
    remote_deleted_at: null,
    local_transform_uri: null,
    upload_size: null,
    upload_width: null,
    upload_height: null,
    upload_cancel_requested: 0,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    ...overrides,
  } as CapturePhotoRow;
}

describe('canExportSession', () => {
  it('allows local_completed with photos (no freeze required)', () => {
    const gate = canExportSession({
      session: session({ active_freeze_id: null, capture_frozen_photo_count: 0 }),
      photos: [photo()],
    });
    expect(gate.ok).toBe(true);
  });

  it('allows uploading sessions so ZIP stays available after handoff', () => {
    const gate = canExportSession({
      session: session({ status: 'uploading', active_freeze_id: null }),
      photos: [photo({ status: 'unstable' })],
    });
    expect(gate.ok).toBe(true);
  });

  it('blocks cancelled, busy, empty, and disabled flag', () => {
    expect(
      canExportSession({ session: session({ status: 'cancelled' }), photos: [photo()] }).ok,
    ).toBe(false);
    expect(
      canExportSession({
        session: session(),
        photos: [photo()],
        exportInProgress: true,
      }).ok,
    ).toBe(false);
    expect(canExportSession({ session: session(), photos: [] }).ok).toBe(false);
    expect(
      canExportSession({
        session: session(),
        photos: [photo()],
        csvExportEnabled: false,
      }).ok,
    ).toBe(false);
  });

  it('isSessionExportableStatus allows handoff and upload statuses', () => {
    expect(isSessionExportableStatus('local_completed')).toBe(true);
    expect(isSessionExportableStatus('review')).toBe(true);
    expect(isSessionExportableStatus('uploading')).toBe(true);
    expect(isSessionExportableStatus('cancelled')).toBe(false);
  });
});

describe('mapLocalCsvExportError', () => {
  it('maps package errors to user-safe kinds', () => {
    expect(mapLocalCsvExportError(new Error('PACKAGE_EXPORT_UNRESOLVED: x')).kind).toBe(
      'unresolved',
    );
    expect(mapLocalCsvExportError(new Error('PACKAGE_PHOTO_READ_FAILED: x')).kind).toBe(
      'photo_read',
    );
    const msg = userMessageForLocalCsvExportError({ kind: 'empty' });
    expect(msg).toMatch(/fotos/i);
    expect(msg.toLowerCase()).not.toContain('password');
  });
});
