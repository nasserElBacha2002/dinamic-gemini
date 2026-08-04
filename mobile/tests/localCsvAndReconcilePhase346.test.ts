import {
  escapeCsvField,
  neutralizeCsvFormula,
  buildCsvDocument,
  LOCAL_CSV_HEADERS,
} from '../src/features/localCsv/csvFormat';
import { buildLocalCsvExport } from '../src/features/localCsv/buildLocalCsvExport';
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

    const result = await buildLocalCsvExport({
      session,
      photos: [photo],
      drafts: [],
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
    expect(result.csv).toContain('LOCAL_PENDING');
    expect(result.checksumSha256.length).toBeGreaterThan(8);
    expect(buildCsvDocument([])).toContain('schema_version');
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
