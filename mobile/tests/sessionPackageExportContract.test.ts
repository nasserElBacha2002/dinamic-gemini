import { buildLocalCsvExport } from '../src/features/localCsv/buildLocalCsvExport';
import { LOCAL_CSV_HEADERS } from '../src/features/localCsv/csvFormat';
import { buildSessionPackageManifest } from '../src/features/localCsv/sessionPackageManifest';
import { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from '../src/features/localCsv/localPackageContract';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';

describe('session package export contract', () => {
  it('CSV schema 1.1 slim headers remain accepted by backend required set', () => {
    const required = [
      'schema_version',
      'export_id',
      'exported_at',
      'device_id',
      'inventory_id',
      'aisle_id',
      'capture_session_id',
      'capture_photo_id',
      'client_file_id',
      'capture_order',
      'captured_at',
      'position_code',
      'internal_code',
      'quantity',
      'quantity_status',
      'detection_status',
      'source',
      'requires_review',
      'error_code',
      'notes',
    ];
    for (const h of required) {
      expect(LOCAL_CSV_HEADERS).toContain(h);
    }
    expect(LOCAL_CSV_HEADERS).toContain('label_id');
    expect(LOCAL_CSV_HEADERS).toContain('position_label_id');
    expect(LOCAL_CSV_HEADERS).toContain('position_payload_raw');
    expect(LOCAL_CSV_HEADERS).not.toContain('inventory_name');
    expect(LOCAL_CSV_HEADERS).not.toContain('freeze_id');
  });

  it('manifest v2 includes legacy fields mirroring CSV ids for consumer compatibility', async () => {
    const now = '2026-08-04T10:00:00.000Z';
    const session: CaptureSessionRow = {
      id: 'session-contract',
      inventory_id: 'inv-contract',
      inventory_name: 'Inv',
      aisle_id: 'aisle-contract',
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
      scan_cursor_date_added: 0,
      scan_cursor_asset_id: '',
      last_valid_cursor_date_added: 0,
      last_valid_cursor_asset_id: '',
      upload_batch_id: null,
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
      active_freeze_id: 'freeze-contract',
      upload_policy: 'MANUAL',
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;
    const photo: CapturePhotoRow = {
      id: 'session-contract:1',
      capture_session_id: 'session-contract',
      asset_id: '1',
      media_store_numeric_id: 1,
      uri: 'file://p.jpg',
      display_name: 'p.jpg',
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
      detected_at: now,
      stable_at: now,
      excluded_at: null,
      client_file_id: 'cf-1',
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
      original_size: null,
      upload_size: null,
      upload_worker_owner: null,
      upload_lease_token: null,
      upload_lease_expires_at: null,
      upload_heartbeat_at: null,
      upload_cancel_requested: 0,
      created_at: now,
      updated_at: now,
    } as CapturePhotoRow;
    const draft = {
      id: 'd1',
      capture_photo_id: photo.id,
      capture_session_id: session.id,
      client_file_id: 'cf-1',
      status: 'RESOLVED',
      internal_code: 'SKU-1',
      product_results_json: JSON.stringify([
        { labelId: 'L1', internalCode: 'SKU-1', quantity: 2 },
      ]),
      position_detected: 0,
      error_code: null,
      quantity_status: 'PRESENT',
      detector_version: '1',
      parser_version: '1',
      prepared_asset_fingerprint: 'fp',
    };
    const built = await buildLocalCsvExport({
      session,
      photos: [photo],
      drafts: [draft as never],
      confirmed: [],
      deviceId: 'device-contract',
      companyId: null,
      clientId: null,
      exportedAt: now,
    });
    const manifest = buildSessionPackageManifest({
      csvSchemaVersion: built.schemaVersion,
      exportId: built.exportId,
      exportedAt: built.exportedAt,
      inventoryId: session.inventory_id,
      aisleId: session.aisle_id,
      captureSessionId: session.id,
      freezeId: session.active_freeze_id,
      freezeGeneration: session.capture_freeze_generation,
      rowCount: built.rowCount,
      expectedPhotoCount: 1,
      includedPhotoCount: 1,
      csvChecksumSha256: built.checksumSha256,
      packageChecksumSha256: 'pkg-fp',
      positionEventCount: built.positionEventCount,
      productResultCount: built.productResultCount,
      rejectedDetectionCount: built.rejectedDetectionCount,
      photos: [
        {
          capture_photo_id: photo.id,
          client_file_id: 'cf-1',
          file_name: '0001_photo.jpg',
        },
      ],
    });
    expect(manifest.package_kind).toBe(LOCAL_PACKAGE_KIND);
    expect(manifest.package_version).toBe(LOCAL_PACKAGE_VERSION);
    expect(manifest.export_id).toBe(built.exportId);
    expect(manifest.inventory_id).toBe(session.inventory_id);
    expect(manifest.aisle_id).toBe(session.aisle_id);
    expect(manifest.capture_session_id).toBe(session.id);
    expect(manifest.checksum_sha256).toBe(built.checksumSha256);
    expect(manifest.csv_checksum_sha256).toBe(built.checksumSha256);
    expect(manifest.row_count).toBe(built.rowCount);
    expect(manifest.summary).toEqual({
      photo_count: 1,
      position_event_count: built.positionEventCount,
      product_result_count: built.productResultCount,
      rejected_detection_count: built.rejectedDetectionCount,
    });
    expect(built.csv).toContain(built.exportId);
    expect(built.csv).toContain(session.inventory_id);
  });
});
