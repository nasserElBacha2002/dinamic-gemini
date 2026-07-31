import { describeProcessButtonBlock } from '../src/features/upload/describeProcessButtonBlock';
import type { CapturePhotoRow } from '../src/database/schema/captureSchema';

function photo(partial: Partial<CapturePhotoRow> & Pick<CapturePhotoRow, 'id' | 'upload_status'>): CapturePhotoRow {
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
    client_file_id: 'cf1',
    sequence_number: 1,
    backend_asset_id: null,
    upload_progress: 0,
    upload_attempts: 1,
    upload_batch_id: 'b1',
    last_upload_error_code: null,
    last_upload_error_message: null,
    last_upload_attempt_at: null,
    next_retry_at: null,
    uploaded_at: null,
    remote_deleted_at: null,
    local_transform_uri: null,
    original_size: null,
    upload_size: null,
    upload_worker_owner: null,
    upload_lease_token: null,
    upload_lease_expires_at: null,
    upload_heartbeat_at: null,
    upload_cancel_requested: 0,
    created_at: '',
    updated_at: '',
    ...partial,
  };
}

describe('describeProcessButtonBlock', () => {
  it('returns null when ready', () => {
    expect(
      describeProcessButtonBlock({
        ready: true,
        photos: [],
        pendingUploads: 0,
        uploadedCount: 1,
      }),
    ).toBeNull();
  });

  it('explains local DB busy without blaming adb reverse', () => {
    const msg = describeProcessButtonBlock({
      ready: false,
      photos: [
        photo({
          id: 'p1',
          upload_status: 'retryable_error',
          last_upload_error_code: 'LOCAL_DB_BUSY',
          last_upload_error_message: 'La base local estaba ocupada. Se reintenta automáticamente.',
        }),
      ],
      pendingUploads: 1,
      uploadedCount: 0,
    });
    expect(msg).toMatch(/base local/i);
    expect(msg).not.toMatch(/adb reverse/);
  });

  it('explains backend unreachable when upload errors mention connection', () => {
    const msg = describeProcessButtonBlock({
      ready: false,
      photos: [
        photo({
          id: 'p1',
          upload_status: 'retryable_error',
          last_upload_error_code: 'NETWORK_ERROR',
          last_upload_error_message: 'No se pudo conectar con el backend.',
        }),
      ],
      pendingUploads: 1,
      uploadedCount: 0,
    });
    expect(msg).toMatch(/No se pudo subir al backend/);
    expect(msg).toMatch(/adb reverse/);
  });

  it('mentions pending uploads when not a connection failure', () => {
    const msg = describeProcessButtonBlock({
      ready: false,
      photos: [photo({ id: 'p1', upload_status: 'queued' })],
      pendingUploads: 2,
      uploadedCount: 0,
    });
    expect(msg).toMatch(/2 carga/);
  });
});
