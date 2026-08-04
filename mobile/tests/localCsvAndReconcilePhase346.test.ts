import {
  escapeCsvField,
  neutralizeCsvFormula,
  buildCsvDocument,
  LOCAL_CSV_HEADERS,
} from '../src/features/localCsv/csvFormat';
import { buildLocalCsvExport, buildLocalCsvRows } from '../src/features/localCsv/buildLocalCsvExport';
import { base64ToUint8Array, uint8ArrayToBase64 } from '../src/features/localCsv/binaryCodec';
import { preparePerTickForNetwork, maxPreparedPendingForNetwork } from '../src/features/upload/prepareParallelism';
import {
  classifyLocalRemotePair,
  reconcileLocalRemoteResults,
} from '../src/features/localRemoteReconciliation/classify';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

describe('Phase 2 prepare parallelism', () => {
  it('uses higher prepare concurrency on wifi', () => {
    expect(preparePerTickForNetwork('wifi')).toBe(3);
    expect(preparePerTickForNetwork('cellular')).toBe(2);
    expect(preparePerTickForNetwork('wifi', { enabled: false, defaultPerTick: 4 })).toBe(4);
    expect(maxPreparedPendingForNetwork('wifi')).toBe(16);
  });
});

describe('Phase 4 local CSV export', () => {
  it('escapes commas quotes and newlines and neutralizes formulas', () => {
    expect(neutralizeCsvFormula('=1+1')).toBe("'=1+1");
    expect(escapeCsvField('a,b')).toBe('"a,b"');
    expect(escapeCsvField('say "hi"')).toBe('"say ""hi"""');
    expect(escapeCsvField('line1\nline2')).toBe('"line1\nline2"');
  });

    it('builds deterministic CSV with stable headers', async () => {
    const now = '2026-01-01T00:00:00.000Z';
    const session = {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-1',
      aisle_name: 'A1',
      status: 'local_completed',
      started_at: now,
      finished_at: null,
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
      preparation_processing_mode: 'UNKNOWN',
      backend_ordered_capture_session_id: null,
      process_attempt_id: null,
      process_idempotency_key: null,
      process_requested_at: null,
      process_confirmed_at: null,
      last_recovery_check_at: null,
      capture_frozen_at: now,
      capture_frozen_photo_count: 1,
      capture_freeze_generation: 1,
      active_freeze_id: null,
      upload_policy: null,
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;

    const photo = {
      id: 'session-1:100',
      capture_session_id: 'session-1',
      asset_id: '100',
      media_store_numeric_id: 100,
      uri: 'file://x.jpg',
      display_name: 'x.jpg',
      mime_type: 'image/jpeg',
      size: 10,
      width: 1,
      height: 1,
      date_added: 10,
      date_modified: 10,
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
      upload_status: 'queued',
      upload_progress: 0,
      upload_attempts: 0,
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
      created_at: now,
      updated_at: now,
    } as CapturePhotoRow;

    const draft = {
      id: 'd-product',
      capture_photo_id: photo.id,
      capture_session_id: 'session-1',
      client_file_id: 'cf-1',
      status: 'RESOLVED' as const,
      raw_value_hash: 'sha256:abc',
      internal_code: 'SKU-100',
      quantity: 3,
      quantity_status: 'PRESENT',
      detected_format: 'PLAIN',
      detected_symbology: 'QR_CODE',
      parser_version: '1.1.0',
      detector_version: 'mlkit-barcode-1.0.0',
      candidate_count: 1,
      error_code: null,
      processing_ms: 10,
      comparison_status: 'PENDING',
      compare_result: null,
      compared_at: null,
      prepared_asset_fingerprint: 'sha256:x',
      scan_owner: null,
      scan_generation: 1,
      sync_status: 'NOT_READY' as const,
      sync_attempt_count: 0,
      sync_next_retry_at: null,
      sync_last_error_code: null,
      server_preliminary_id: null,
      synced_at: null,
      sync_lease_token: null,
      sync_lease_expires_at: null,
      detected_at: now,
      created_at: now,
      updated_at: now,
    };

    await expect(
      buildLocalCsvExport({
        session,
        photos: [photo],
        drafts: [],
        confirmed: [],
        deviceId: 'dev-1',
        companyId: null,
        clientId: 'client-1',
        exportId: 'export-pending',
        exportedAt: now,
      }),
    ).rejects.toThrow(/PACKAGE_EXPORT_UNRESOLVED/);

    const result = await buildLocalCsvExport({
      session,
      photos: [photo],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev-1',
      companyId: null,
      clientId: 'client-1',
      exportId: 'export-1',
      exportedAt: now,
    });
    expect(result.rowCount).toBe(1);
    expect(result.csv.startsWith(LOCAL_CSV_HEADERS.join(','))).toBe(true);
    expect(result.csv).toContain('export-1');
    expect(result.csv).toContain('LOCAL_CODE_SCAN');
    expect(result.csv).toContain('SKU-100');
    expect(result.checksumSha256.length).toBeGreaterThan(8);
    expect(buildCsvDocument([])).toContain('schema_version');
  });

  it('exports DINAMIC_POSITION label_id as position_code and carries it to later photos', () => {
    const now = '2026-01-01T00:00:00.000Z';
    const session = {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-1',
      aisle_name: 'A1',
      status: 'local_completed',
      started_at: now,
      finished_at: null,
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
      preparation_processing_mode: 'UNKNOWN',
      backend_ordered_capture_session_id: null,
      process_attempt_id: null,
      process_idempotency_key: null,
      process_requested_at: null,
      process_confirmed_at: null,
      last_recovery_check_at: null,
      capture_frozen_at: now,
      capture_frozen_photo_count: 2,
      capture_freeze_generation: 1,
      active_freeze_id: null,
      upload_policy: null,
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;

    const photo = (id: string, seq: number, assetId: string) =>
      ({
        id,
        capture_session_id: 'session-1',
        asset_id: assetId,
        media_store_numeric_id: Number(assetId),
        uri: `file://${assetId}.jpg`,
        display_name: `${assetId}.jpg`,
        mime_type: 'image/jpeg',
        size: 10,
        width: 1,
        height: 1,
        date_added: seq,
        date_modified: seq,
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
        client_file_id: `cf-${assetId}`,
        sequence_number: seq,
        backend_asset_id: null,
        upload_status: 'queued',
        upload_progress: 0,
        upload_attempts: 0,
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
        created_at: now,
        updated_at: now,
      }) as CapturePhotoRow;

    const labelPhoto = photo('session-1:1', 1, '1');
    const productPhoto = photo('session-1:2', 2, '2');

    const rows = buildLocalCsvRows({
      session,
      photos: [labelPhoto, productPhoto],
      drafts: [
        {
          id: 'd1',
          capture_photo_id: labelPhoto.id,
          capture_session_id: 'session-1',
          client_file_id: 'cf-1',
          status: 'DETECTED_UNVERIFIED',
          raw_value_hash: 'sha256:abc',
          internal_code: 'pos-label-public-1',
          quantity: null,
          quantity_status: 'MISSING',
          detected_format: 'PLAIN',
          detected_symbology: 'QR_CODE',
          parser_version: '1.1.0',
          detector_version: 'mlkit-barcode-1.0.0',
          candidate_count: 1,
          error_code: 'POSITION_LABEL_DETECTED',
          processing_ms: 10,
          comparison_status: 'PENDING',
          compare_result: null,
          compared_at: null,
          prepared_asset_fingerprint: 'sha256:x',
          scan_owner: null,
          scan_generation: 1,
          sync_status: 'NOT_READY',
          sync_attempt_count: 0,
          sync_next_retry_at: null,
          sync_last_error_code: null,
          server_preliminary_id: null,
          synced_at: null,
          sync_lease_token: null,
          sync_lease_expires_at: null,
          detected_at: now,
          created_at: now,
          updated_at: now,
        },
        {
          id: 'd2',
          capture_photo_id: productPhoto.id,
          capture_session_id: 'session-1',
          client_file_id: 'cf-2',
          status: 'RESOLVED',
          raw_value_hash: 'sha256:def',
          internal_code: 'SKU-99',
          quantity: 3,
          quantity_status: 'PRESENT',
          detected_format: 'PIPE',
          detected_symbology: 'QR_CODE',
          parser_version: '1.1.0',
          detector_version: 'mlkit-barcode-1.0.0',
          candidate_count: 1,
          error_code: null,
          processing_ms: 10,
          comparison_status: 'PENDING',
          compare_result: null,
          compared_at: null,
          prepared_asset_fingerprint: 'sha256:y',
          scan_owner: null,
          scan_generation: 1,
          sync_status: 'NOT_READY',
          sync_attempt_count: 0,
          sync_next_retry_at: null,
          sync_last_error_code: null,
          server_preliminary_id: null,
          synced_at: null,
          sync_lease_token: null,
          sync_lease_expires_at: null,
          detected_at: now,
          created_at: now,
          updated_at: now,
        },
      ],
      confirmed: [],
      deviceId: 'dev-1',
      companyId: null,
      clientId: 'client-1',
      exportId: 'export-pos-1',
      exportedAt: now,
    });

    expect(rows).toHaveLength(2);
    expect(rows[0]?.position_code).toBe('pos-label-public-1');
    expect(rows[0]?.position_status).toBe('LABEL_DETECTED');
    expect(rows[0]?.internal_code).toBe('');
    expect(rows[0]?.source).toBe('LOCAL_POSITION_LABEL');
    expect(rows[1]?.position_code).toBe('pos-label-public-1');
    expect(rows[1]?.position_status).toBe('INFERRED_FROM_PRIOR_LABEL');
    expect(rows[1]?.internal_code).toBe('SKU-99');
    expect(rows[1]?.source).toBe('LOCAL_CODE_SCAN');
  });
});

describe('binary codec for ZIP packaging', () => {
  it('round-trips base64', () => {
    const original = new Uint8Array([0, 1, 2, 255, 128, 7]);
    const b64 = uint8ArrayToBase64(original);
    expect(base64ToUint8Array(b64)).toEqual(original);
  });
});

describe('local package contract constants', () => {
  it('exports package kind and version 2', () => {
    const {
      LOCAL_PACKAGE_KIND,
      LOCAL_PACKAGE_VERSION,
    } = require('../src/features/localCsv/localPackageContract') as {
      LOCAL_PACKAGE_KIND: string;
      LOCAL_PACKAGE_VERSION: number;
    };
    expect(LOCAL_PACKAGE_KIND).toBe('DINAMIC_LOCAL_AISLE_EXPORT');
    expect(LOCAL_PACKAGE_VERSION).toBe(2);
  });
});

describe('Phase 6 local-remote reconciliation', () => {
  it('classifies match conflict and local-only', () => {
    expect(
      classifyLocalRemotePair(
        { internalCode: 'A', quantity: 1, source: 'LOCAL' },
        { internalCode: 'A', quantity: 1, source: 'SERVER' },
      ).outcome,
    ).toBe('MATCHED');
    expect(
      classifyLocalRemotePair(
        { internalCode: 'A', quantity: 1, source: 'LOCAL' },
        { internalCode: 'B', quantity: 1, source: 'SERVER' },
      ).outcome,
    ).toBe('CONFLICT');
    expect(
      classifyLocalRemotePair({ internalCode: 'A', quantity: 1, source: 'LOCAL' }, null).outcome,
    ).toBe('LOCAL_ONLY');
    const rows = reconcileLocalRemoteResults([
      {
        capturePhotoId: 'p1',
        clientFileId: 'c1',
        local: { internalCode: 'A', quantity: 2, source: 'LOCAL' },
        server: { internalCode: 'A', quantity: 3, source: 'SERVER' },
      },
    ]);
    expect(rows[0]?.outcome).toBe('CONFLICT');
    expect(rows[0]?.notes).toBe('quantity_mismatch');
  });
});
