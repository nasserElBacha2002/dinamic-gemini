import {
  buildSupplierImportNotes,
  isLikelyRawSegmentedPayload,
  positionFromRecognitionSnapshot,
  productsFromRecognitionSnapshot,
} from '../src/features/localCsv/supplierExportSemantics';
import { buildLocalCsvRows } from '../src/features/localCsv/buildLocalCsvExport';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { EMPTY_CURSOR } from '../src/core/compositeCursor';

const ITEM_SNAPSHOT = JSON.stringify({
  offline: true,
  client_supplier_id: 'sup-b',
  item: {
    status: 'VALID',
    profile_id: 'prof-item',
    profile_version: 10,
    label_id: 'LPNA000184',
    sku: 'SKU773421',
    quantity: 24,
  },
  position: { profile_source: 'SUPPLIER', missing: false },
});

const POSITION_SNAPSHOT = JSON.stringify({
  offline: true,
  client_supplier_id: 'sup-b',
  position: {
    status: 'VALID',
    profile_id: 'prof-pos',
    profile_version: 3,
    position_id: 'A04-R-02',
    pallet: '04',
    side: 'RIGHT',
    level: '02',
  },
});

describe('supplier export semantics', () => {
  it('detects raw segmented payloads', () => {
    expect(isLikelyRawSegmentedPayload('LPNA000184|SKU773421|24')).toBe(true);
    expect(isLikelyRawSegmentedPayload('A04-R-02|04|RIGHT|02')).toBe(true);
    expect(isLikelyRawSegmentedPayload('SKU773421')).toBe(false);
    expect(isLikelyRawSegmentedPayload('A|1')).toBe(false);
  });

  it('extracts ITEM fields from recognition snapshot', () => {
    const products = productsFromRecognitionSnapshot(ITEM_SNAPSHOT);
    expect(products).toEqual([
      { labelId: 'LPNA000184', internalCode: 'SKU773421', quantity: 24 },
    ]);
  });

  it('extracts POSITION fields from recognition snapshot', () => {
    const pos = positionFromRecognitionSnapshot(POSITION_SNAPSHOT);
    expect(pos?.positionCode).toBe('A04-R-02');
    expect(pos?.pallet).toBe('04');
    expect(pos?.side).toBe('RIGHT');
    expect(pos?.level).toBe('02');
  });

  it('does not export raw segmented string as SKU when snapshot has semantic ITEM', () => {
    const now = '2026-01-01T00:00:00.000Z';
    const session = {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-local',
      aisle_name: 'Local',
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
      active_freeze_id: null,
      upload_policy: null,
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;
    const photo = {
      id: 'photo-item',
      capture_session_id: 'session-1',
      asset_id: 'asset-1',
      client_file_id: 'cf-1',
      status: 'stable',
      upload_status: 'not_queued',
      sequence_number: 1,
      date_added: 1,
      detected_at: now,
      stable_at: now,
      created_at: now,
    } as CapturePhotoRow;

    const rows = buildLocalCsvRows({
      session,
      photos: [photo],
      drafts: [
        {
          capture_photo_id: 'photo-item',
          capture_session_id: 'session-1',
          client_file_id: 'cf-1',
          status: 'RESOLVED',
          internal_code: 'LPNA000184|SKU773421|24',
          product_results_json: null,
          recognition_profile_snapshot_json: ITEM_SNAPSHOT,
          position_detected: 0,
          error_code: null,
        } as never,
      ],
      confirmed: [],
      deviceId: 'dev-1',
      companyId: null,
      clientId: 'client-1',
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]?.internal_code).toBe('SKU773421');
    expect(rows[0]?.label_id).toBe('LPNA000184');
    expect(rows[0]?.quantity).toBe('24');
    expect(rows[0]?.internal_code).not.toContain('|');
  });

  it('exports POSITION-only row without product SKU', () => {
    const now = '2026-01-01T00:00:00.000Z';
    const session = {
      id: 'session-1',
      inventory_id: 'inv-1',
      inventory_name: 'Inv',
      aisle_id: 'aisle-local',
      aisle_name: 'Local',
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
      active_freeze_id: null,
      upload_policy: null,
      created_at: now,
      updated_at: now,
    } as CaptureSessionRow;
    const photo = {
      id: 'photo-pos',
      capture_session_id: 'session-1',
      asset_id: 'asset-2',
      client_file_id: 'cf-2',
      status: 'stable',
      upload_status: 'not_queued',
      sequence_number: 2,
      date_added: 2,
      detected_at: now,
      stable_at: now,
      created_at: now,
    } as CapturePhotoRow;

    const rows = buildLocalCsvRows({
      session,
      photos: [photo],
      drafts: [
        {
          capture_photo_id: 'photo-pos',
          capture_session_id: 'session-1',
          client_file_id: 'cf-2',
          status: 'DETECTED_UNVERIFIED',
          internal_code: 'A04-R-02|04|RIGHT|02',
          product_results_json: null,
          recognition_profile_snapshot_json: POSITION_SNAPSHOT,
          position_detected: 1,
          error_code: 'POSITION_LABEL_DETECTED',
        } as never,
      ],
      confirmed: [],
      deviceId: 'dev-1',
      companyId: null,
      clientId: 'client-1',
    });

    expect(rows).toHaveLength(1);
    expect(rows[0]?.source).toBe('LOCAL_POSITION_LABEL');
    expect(rows[0]?.internal_code).toBe('');
    expect(rows[0]?.position_code).toBe('A04-R-02');
    expect(rows[0]?.position_label_id).toBe('A04-R-02');
  });

  it('builds supplier import notes for backend revalidation', () => {
    const notes = buildSupplierImportNotes({
      snapshotJson: ITEM_SNAPSHOT,
      rawPayload: 'LPNA000184|SKU773421|24',
      labelKind: 'ITEM',
    });
    expect(notes).toContain('supplier_import');
    expect(notes).toContain('prof-item');
    expect(notes).toContain('"profile_version":10');
  });
});
