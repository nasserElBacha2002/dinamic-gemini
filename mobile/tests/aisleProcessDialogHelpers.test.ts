/**
 * Unit tests for Procesar pasillo hub helpers.
 */

import {
  buildLocalResultListItems,
  buildLocalResultsUploadIdempotencyKey,
  canRestoreExcludedPhoto,
  countExcludedPhotos,
  countPendingLocalResults,
  isExcludedPhoto,
  isSessionSealedForPhotoRestore,
} from '../src/features/processing/aisleProcessDialogHelpers';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { ConfirmedLocalResultRow } from '../src/database/repositories/confirmedLocalResultRepository';

function photo(partial: Partial<CapturePhotoRow> & Pick<CapturePhotoRow, 'id'>): CapturePhotoRow {
  return {
    capture_session_id: 's1',
    asset_id: 'a1',
    media_store_numeric_id: null,
    uri: 'file://x',
    display_name: 'x.jpg',
    mime_type: 'image/jpeg',
    size: 1,
    width: 1,
    height: 1,
    date_added: 0,
    date_modified: 0,
    bucket_id: null,
    relative_path: null,
    status: 'stable',
    rejection_reason: null,
    stability_checks: 0,
    stability_attempts: 0,
    stability_error: null,
    last_stability_attempt_at: null,
    detected_at: null,
    stable_at: null,
    excluded_at: null,
    client_file_id: null,
    sequence_number: null,
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
    upload_cancel_requested: 0,
    upload_worker_owner: null,
    upload_lease_expires_at: null,
    local_transform_uri: null,
    original_size: null,
    upload_size: null,
    created_at: '',
    updated_at: '',
    ...partial,
  } as CapturePhotoRow;
}

describe('aisleProcessDialogHelpers', () => {
  it('counts excluded photos by capture status and upload status', () => {
    const photos = [
      photo({ id: '1', status: 'excluded' }),
      photo({ id: '2', upload_status: 'excluded' }),
      photo({ id: '3', upload_status: 'uploaded' }),
      photo({ id: '4', upload_status: 'remote_deleted' }),
    ];
    expect(countExcludedPhotos(photos)).toBe(3);
    expect(isExcludedPhoto(photos[2]!)).toBe(false);
  });

  it('counts pending local results', () => {
    const rows = [
      { sync_status: 'PENDING' },
      { sync_status: 'SYNCED' },
      { sync_status: 'FAILED_TERMINAL' },
      { sync_status: 'RETRY_SCHEDULED' },
    ] as ConfirmedLocalResultRow[];
    expect(countPendingLocalResults(rows)).toBe(3);
  });

  it('builds stable idempotency key for retries', () => {
    const a = buildLocalResultsUploadIdempotencyKey({
      clientId: 'c1',
      inventoryId: 'inv',
      aisleId: 'aisle',
      sessionId: 'sess',
    });
    const b = buildLocalResultsUploadIdempotencyKey({
      clientId: 'c1',
      inventoryId: 'inv',
      aisleId: 'aisle',
      sessionId: 'sess',
    });
    expect(a).toBe(b);
    expect(a).toContain('mobile-local-results:c1:inv:aisle:sess');
  });

  it('marks completed sessions as sealed for restore', () => {
    expect(
      isSessionSealedForPhotoRestore({ status: 'completed' } as CaptureSessionRow),
    ).toBe(true);
    expect(
      isSessionSealedForPhotoRestore({ status: 'ready_to_process' } as CaptureSessionRow),
    ).toBe(false);
    expect(
      isSessionSealedForPhotoRestore({ status: 'finishing' } as CaptureSessionRow),
    ).toBe(false);
  });

  it('allows re-queue of never-uploaded queue exclusions before a job starts', () => {
    const session = { status: 'finishing', backend_job_id: null } as CaptureSessionRow;
    const excludedQueue = photo({
      id: 'q1',
      upload_status: 'excluded',
      backend_asset_id: null,
    });
    expect(canRestoreExcludedPhoto(session, excludedQueue)).toBe(true);
    expect(
      canRestoreExcludedPhoto(
        { status: 'ready_to_process', backend_job_id: 'job-1' } as CaptureSessionRow,
        excludedQueue,
      ),
    ).toBe(false);
  });

  it('orders local result list by confirmed_at DESC', () => {
    const rows = [
      {
        id: 'a',
        confirmed_at: '2026-07-31T10:00:00.000Z',
        confirmed_internal_code: '111',
        sync_status: 'PENDING',
        sync_last_error_code: null,
      },
      {
        id: 'b',
        confirmed_at: '2026-07-31T12:00:00.000Z',
        confirmed_internal_code: '222',
        sync_status: 'SYNCED',
        sync_last_error_code: null,
      },
    ] as ConfirmedLocalResultRow[];
    const items = buildLocalResultListItems(rows);
    expect(items[0]!.localResultId).toBe('b');
    expect(items[1]!.localResultId).toBe('a');
  });
});
