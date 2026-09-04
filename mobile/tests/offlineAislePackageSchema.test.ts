import {
  collectProfileEntries,
  finalizeCaptureRawHashes,
  mapPhotoToCapture,
  parseProductResultsWithRaw,
  sortCapturesDeterministic,
} from '../src/features/offlineAisleExport/captureMapper';
import { buildZipBytes } from '../src/features/offlineAisleExport/boundedMemoryZipWriter';
import { selectLatestSession } from '../src/features/offlineAisleExport/sessionSelection';
import {
  validatePackageModel,
  buildManifestWithIntegrity,
  stableJson,
  computePackageIntegrity,
  buildExpectedIntegrityPaths,
} from '../src/features/offlineAisleExport/packageValidator';
import { OFFLINE_AISLE_FORMAT, OFFLINE_AISLE_SCHEMA_VERSION } from '../src/features/offlineAisleExport/constants';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { LocalDetectionDraftRow } from '../src/database/repositories/localDetectionDraftRepository';

const ITEM_SNAPSHOT = JSON.stringify({
  offline: true,
  client_supplier_id: 'sup-b',
  item: {
    status: 'VALID',
    profile_id: 'prof-item',
    profile_version: 10,
    profile_source: 'SUPPLIER',
    label_id: 'LPNA000184',
    sku: 'SKU773421',
    quantity: 24,
  },
});

const POSITION_SNAPSHOT = JSON.stringify({
  offline: true,
  client_supplier_id: 'sup-b',
  position: {
    status: 'VALID',
    profile_id: 'prof-pos',
    profile_version: 3,
    profile_source: 'SUPPLIER',
    position_id: 'A04-R-02',
    pallet: '04',
    side: 'RIGHT',
    level: '02',
  },
});

const MIXED_DINAMIC_ITEM_SNAPSHOT = JSON.stringify({
  client_supplier_id: 'sup-b',
  item: {
    status: 'VALID',
    profile_id: 'din-item',
    profile_version: 1,
    profile_source: 'DINAMIC',
    label_id: 'L1',
    sku: 'S1',
    quantity: 1,
  },
  position: {
    status: 'VALID',
    profile_id: 'prof-pos',
    profile_version: 3,
    profile_source: 'SUPPLIER',
    position_id: 'A04-R-02',
    pallet: '04',
    side: 'RIGHT',
    level: '02',
  },
});

const MIXED_SUPPLIER_ITEM_SNAPSHOT = JSON.stringify({
  client_supplier_id: 'sup-b',
  item: {
    status: 'VALID',
    profile_id: 'prof-item',
    profile_version: 10,
    profile_source: 'SUPPLIER',
    label_id: 'LPNA000184',
    sku: 'SKU773421',
    quantity: 24,
  },
  position: {
    status: 'VALID',
    profile_id: 'din-pos',
    profile_version: 2,
    profile_source: 'DINAMIC',
    position_id: 'A04-R-02',
    pallet: '04',
    side: 'RIGHT',
    level: '02',
  },
});

function session(overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
  const now = '2026-01-01T00:00:00.000Z';
  return {
    id: 'sess-1',
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_id: 'aisle-1',
    aisle_name: 'Pasillo A',
    status: 'local_completed',
    started_at: now,
    finished_at: now,
    initial_asset_id: null,
    initial_date_added: null,
    initial_date_modified: null,
    initial_display_name: null,
    initial_size: null,
    initial_bucket_id: null,
    scan_cursor_date_added: null as never,
    scan_cursor_asset_id: null as never,
    last_valid_cursor_date_added: null as never,
    last_valid_cursor_asset_id: null as never,
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
    active_freeze_id: null,
    upload_policy: null,
    active_position_json: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  } as unknown as CaptureSessionRow;
}

function photo(id: string): CapturePhotoRow {
  const now = '2026-01-01T00:00:00.000Z';
  return {
    id,
    capture_session_id: 'sess-1',
    asset_id: `asset-${id}`,
    media_store_numeric_id: 1,
    uri: `file://${id}.jpg`,
    display_name: `${id}.jpg`,
    mime_type: 'image/jpeg',
    size: 100,
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
    client_file_id: `cf-${id}`,
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
    original_size: null,
    upload_worker_owner: null,
    upload_lease_token: null,
    upload_lease_expires_at: null,
    upload_heartbeat_at: null,
    created_at: now,
    updated_at: now,
  } as unknown as CapturePhotoRow;
}

function itemDraft(): LocalDetectionDraftRow {
  return {
    id: 'd-item',
    capture_photo_id: 'cap-item',
    capture_session_id: 'sess-1',
    client_file_id: 'cf-cap-item',
    status: 'RESOLVED',
    raw_value_hash: 'hash',
    internal_code: 'SKU773421',
    quantity: 24,
    quantity_status: 'PRESENT',
    detected_format: 'SUPPLIER',
    detected_symbology: 'QR_CODE',
    parser_version: '1',
    detector_version: '1',
    candidate_count: 1,
    error_code: null,
    processing_ms: 1,
    comparison_status: null,
    compare_result: null,
    compared_at: null,
    prepared_asset_fingerprint: 'fp',
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
    position_snapshot_json: null,
    label_id: 'LPNA000184',
    product_results_json: JSON.stringify([
      {
        labelId: 'LPNA000184',
        internalCode: 'SKU773421',
        quantity: 24,
        formatVersion: 'SUPPLIER',
        validationStatus: 'VALID',
        rawPayload: 'LPNA000184|SKU773421|24',
      },
    ]),
    rejections_json: null,
    position_detected: 0,
    recognition_profile_snapshot_json: ITEM_SNAPSHOT,
    recognition_context: 'OFFLINE',
    detected_at: '2026-01-01T00:00:00.000Z',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  };
}

function positionDraft(): LocalDetectionDraftRow {
  const raw = 'A04-R-02|04|RIGHT|02';
  return {
    ...itemDraft(),
    id: 'd-pos',
    capture_photo_id: 'cap-pos',
    client_file_id: 'cf-cap-pos',
    status: 'DETECTED_UNVERIFIED',
    internal_code: null,
    quantity: null,
    label_id: null,
    product_results_json: null,
    error_code: 'POSITION_LABEL_DETECTED',
    position_detected: 1,
    recognition_profile_snapshot_json: POSITION_SNAPSHOT,
    position_snapshot_json: JSON.stringify({
      labelId: 'A04-R-02',
      positionLabelId: 'A04-R-02',
      displayName: 'A04-R-02',
      rawPayload: raw,
      sourcePayload: raw,
    }),
  };
}

function mixedDraft(snapshot: string, photoId: string, itemRaw: string, posRaw: string): LocalDetectionDraftRow {
  return {
    ...itemDraft(),
    id: `d-${photoId}`,
    capture_photo_id: photoId,
    client_file_id: `cf-${photoId}`,
    status: 'RESOLVED',
    position_detected: 1,
    recognition_profile_snapshot_json: snapshot,
    product_results_json: JSON.stringify([
      {
        labelId: 'LPNA000184',
        internalCode: 'SKU773421',
        quantity: 24,
        formatVersion: 'SUPPLIER',
        rawPayload: itemRaw,
      },
    ]),
    position_snapshot_json: JSON.stringify({ rawPayload: posRaw, sourcePayload: posRaw }),
  };
}

describe('offline aisle package schema / mapper', () => {
  it('1. PRODUCT only Supplier preserves ITEM provenance', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const [finalCap] = await finalizeCaptureRawHashes([cap]);
    expect(finalCap!.result_kind).toBe('PRODUCT');
    expect(finalCap!.recognitions.item?.raw_evidence.raw_payload).toBe('LPNA000184|SKU773421|24');
    expect(finalCap!.recognitions.position).toBeNull();
    expect(finalCap!.recognitions.item?.profile_ref).toBe('item:prof-item:v10');
  });

  it('2. POSITION_ONLY Supplier preserves POSITION provenance', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-pos'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: positionDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.result_kind).toBe('POSITION_ONLY');
    expect(cap.recognitions.position?.raw_evidence.raw_payload).toBe('A04-R-02|04|RIGHT|02');
    expect(cap.recognitions.item).toBeNull();
    expect(cap.result.product).toBeNull();
  });

  it('3. PRODUCT_WITH_POSITION preserves distinct raws and profiles', async () => {
    const itemRaw = 'LPNA000184|SKU773421|24';
    const posRaw = 'A04-R-02|04|RIGHT|02';
    const cap = mapPhotoToCapture({
      photo: photo('cap-mixed'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: mixedDraft(
        JSON.stringify({
          client_supplier_id: 'sup-b',
          item: JSON.parse(ITEM_SNAPSHOT).item,
          position: JSON.parse(POSITION_SNAPSHOT).position,
        }),
        'cap-mixed',
        itemRaw,
        posRaw,
      ),
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.result_kind).toBe('PRODUCT_WITH_POSITION');
    expect(cap.recognitions.item?.raw_evidence.raw_payload).toBe(itemRaw);
    expect(cap.recognitions.position?.raw_evidence.raw_payload).toBe(posRaw);
    expect(cap.recognitions.item?.profile_ref).toBe('item:prof-item:v10');
    expect(cap.recognitions.position?.profile_ref).toBe('position:prof-pos:v3');
    const profiles = collectProfileEntries([cap]);
    expect(profiles).toHaveLength(2);
  });

  it('4. Mixed ITEM DINAMIC / POSITION SUPPLIER', () => {
    const draft = {
      ...mixedDraft(MIXED_DINAMIC_ITEM_SNAPSHOT, 'cap-md', 'L1|S1|1', 'A04-R-02|04|RIGHT|02'),
      product_results_json: JSON.stringify([
        {
          labelId: 'L1',
          internalCode: 'S1',
          quantity: 1,
          formatVersion: 'DINAMIC',
          rawPayload: 'L1|S1|1',
        },
      ]),
    };
    const cap = mapPhotoToCapture({
      photo: photo('cap-md'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft,
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.recognitions.item?.source).toBe('DINAMIC');
    expect(cap.recognitions.position?.source).toBe('SUPPLIER');
  });

  it('5. Mixed ITEM SUPPLIER / POSITION DINAMIC', () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-ms'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: mixedDraft(
        MIXED_SUPPLIER_ITEM_SNAPSHOT,
        'cap-ms',
        'LPNA000184|SKU773421|24',
        'A04-R-02|04|RIGHT|02',
      ),
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.recognitions.item?.source).toBe('SUPPLIER');
    expect(cap.recognitions.position?.source).toBe('DINAMIC');
  });

  it('6. label_id null + valid SKU is transported', () => {
    const draft = {
      ...itemDraft(),
      product_results_json: JSON.stringify([
        {
          labelId: null,
          internalCode: 'ABC123',
          quantity: 5,
          formatVersion: 'SUPPLIER',
          rawPayload: '|ABC123|5',
        },
      ]),
      recognition_profile_snapshot_json: JSON.stringify({
        client_supplier_id: 'sup-b',
        item: {
          status: 'VALID',
          profile_id: 'p',
          profile_version: 10,
          profile_source: 'SUPPLIER',
          label_id: null,
          sku: 'ABC123',
          quantity: 5,
        },
      }),
    };
    const cap = mapPhotoToCapture({
      photo: photo('cap-null-label'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft,
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.result.product?.label_id).toBeNull();
    expect(cap.result.product?.sku).toBe('ABC123');
    expect(cap.result.product?.quantity).toBe(5);
  });

  it('7. optional missing asset produces PARTIAL-valid model', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: true,
      requireAssets: false,
    });
    const missingAssetCap = {
      ...cap,
      asset: {
        ...cap.asset!,
        included: false,
        path: null,
        size_bytes: null,
        sha256: null,
        asset_missing: true,
      },
    };
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(missingAssetCap) };
    const integrity = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 1,
          asset_count: 0,
          include_assets: true,
          completeness: 'PARTIAL',
        },
        {},
      ),
      aisle,
      profiles: [],
      captures: [missingAssetCap],
      captureFiles,
      assetHashes: {},
    });
    const manifest = buildManifestWithIntegrity(
      {
        format: OFFLINE_AISLE_FORMAT,
        schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
        export_id: 'e1',
        created_at: '2026-01-01T00:00:00.000Z',
        app_version: '0.3.0',
        inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
        aisle: {
          id: 'aisle-1',
          name: 'A',
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          operational_status: 'local_completed',
        },
        supplier: { client_supplier_id: 'sup-b', name: 'S' },
        capture_count: 1,
        asset_count: 0,
        include_assets: true,
        completeness: 'PARTIAL',
      },
      integrity,
    );
    await expect(
      validatePackageModel({
        manifest,
        aisle,
        profiles: [],
        captures: [missingAssetCap],
        captureFiles,
        assetHashes: {},
      }),
    ).resolves.toBeUndefined();
  });

  it('8. required missing asset fails validation when marked included', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: true,
      requireAssets: true,
    });
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(cap) };
    const integrity = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 1,
          asset_count: 1,
          include_assets: true,
          completeness: 'COMPLETE',
        },
        {},
      ),
      aisle,
      profiles: [],
      captures: [cap],
      captureFiles,
      assetHashes: {},
    });
    const manifest = buildManifestWithIntegrity(
      {
        format: OFFLINE_AISLE_FORMAT,
        schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
        export_id: 'e1',
        created_at: '2026-01-01T00:00:00.000Z',
        app_version: '0.3.0',
        inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
        aisle: {
          id: 'aisle-1',
          name: 'A',
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          operational_status: 'local_completed',
        },
        supplier: { client_supplier_id: 'sup-b', name: 'S' },
        capture_count: 1,
        asset_count: 1,
        include_assets: true,
        completeness: 'COMPLETE',
      },
      integrity,
    );
    await expect(
      validatePackageModel({
        manifest,
        aisle,
        profiles: [],
        captures: [cap],
        captureFiles,
        assetHashes: {},
      }),
    ).rejects.toMatchObject({ code: 'ASSET_MISSING' });
  });

  it('9. raw hash mismatch rejected', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const badCap = {
      ...cap,
      recognitions: {
        ...cap.recognitions,
        item: cap.recognitions.item
          ? {
              ...cap.recognitions.item,
              raw_evidence: {
                raw_payload: cap.recognitions.item.raw_evidence.raw_payload,
                raw_payload_sha256: 'deadbeef',
              },
            }
          : null,
      },
    };
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(badCap) };
    const integrity = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 1,
          asset_count: 0,
          include_assets: false,
          completeness: 'COMPLETE',
        },
        {},
      ),
      aisle,
      profiles: [],
      captures: [badCap],
      captureFiles,
      assetHashes: {},
    });
    const manifest = buildManifestWithIntegrity(
      {
        format: OFFLINE_AISLE_FORMAT,
        schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
        export_id: 'e1',
        created_at: '2026-01-01T00:00:00.000Z',
        app_version: '0.3.0',
        inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
        aisle: {
          id: 'aisle-1',
          name: 'A',
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          operational_status: 'local_completed',
        },
        supplier: { client_supplier_id: 'sup-b', name: 'S' },
        capture_count: 1,
        asset_count: 0,
        include_assets: false,
        completeness: 'COMPLETE',
      },
      integrity,
    );
    await expect(
      validatePackageModel({
        manifest,
        aisle,
        profiles: [],
        captures: [badCap],
        captureFiles,
        assetHashes: {},
      }),
    ).rejects.toMatchObject({ code: 'PACKAGE_HASH_FAILED' });
  });

  it('10. manifest capture_count mismatch rejected', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(cap) };
    const integrity = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 99,
          asset_count: 0,
          include_assets: false,
          completeness: 'COMPLETE',
        },
        {},
      ),
      aisle,
      profiles: [],
      captures: [cap],
      captureFiles,
      assetHashes: {},
    });
    const manifest = buildManifestWithIntegrity(
      {
        format: OFFLINE_AISLE_FORMAT,
        schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
        export_id: 'e1',
        created_at: '2026-01-01T00:00:00.000Z',
        app_version: '0.3.0',
        inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
        aisle: {
          id: 'aisle-1',
          name: 'A',
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          operational_status: 'local_completed',
        },
        supplier: { client_supplier_id: 'sup-b', name: 'S' },
        capture_count: 99,
        asset_count: 0,
        include_assets: false,
        completeness: 'COMPLETE',
      },
      integrity,
    );
    await expect(
      validatePackageModel({
        manifest,
        aisle,
        profiles: [],
        captures: [cap],
        captureFiles,
        assetHashes: {},
      }),
    ).rejects.toMatchObject({ code: 'PACKAGE_HASH_FAILED' });
  });

  it('11. manifest asset_count mismatch rejected', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(cap) };
    await expect(
      validatePackageModel({
        manifest: buildManifestWithIntegrity(
          {
            format: OFFLINE_AISLE_FORMAT,
            schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
            export_id: 'e1',
            created_at: '2026-01-01T00:00:00.000Z',
            app_version: '0.3.0',
            inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
            aisle: {
              id: 'aisle-1',
              name: 'A',
              origin: 'LOCAL',
              sync_status: 'LOCAL_ONLY',
              operational_status: 'local_completed',
            },
            supplier: { client_supplier_id: 'sup-b', name: 'S' },
            capture_count: 1,
            asset_count: 5,
            include_assets: false,
            completeness: 'COMPLETE',
          },
          {},
        ),
        aisle,
        profiles: [],
        captures: [cap],
        captureFiles,
        assetHashes: {},
      }),
    ).rejects.toMatchObject({ code: 'PACKAGE_HASH_FAILED' });
  });

  it('12. duplicate capture IDs rejected', async () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const aisle = {
      id: 'aisle-1',
      inventory_id: 'inv-1',
      client_supplier_id: 'sup-b',
      name: 'A',
      created_offline_at: null,
      completed_at: null,
      origin: 'LOCAL',
      sync_status: 'LOCAL_ONLY',
    };
    const captureFiles = { [`captures/${cap.capture_id}.json`]: stableJson(cap) };
    const integrity = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 2,
          asset_count: 0,
          include_assets: false,
          completeness: 'COMPLETE',
        },
        {},
      ),
      aisle,
      profiles: [],
      captures: [cap, cap],
      captureFiles,
      assetHashes: {},
    });
    const manifest = buildManifestWithIntegrity(
      {
        format: OFFLINE_AISLE_FORMAT,
        schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
        export_id: 'e1',
        created_at: '2026-01-01T00:00:00.000Z',
        app_version: '0.3.0',
        inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
        aisle: {
          id: 'aisle-1',
          name: 'A',
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          operational_status: 'local_completed',
        },
        supplier: { client_supplier_id: 'sup-b', name: 'S' },
        capture_count: 2,
        asset_count: 0,
        include_assets: false,
        completeness: 'COMPLETE',
      },
      integrity,
    );
    await expect(
      validatePackageModel({
        manifest,
        aisle,
        profiles: [],
        captures: [cap, cap],
        captureFiles,
        assetHashes: {},
      }),
    ).rejects.toMatchObject({ code: 'CAPTURE_ID_DUPLICATED' });
  });

  it('13. multiple profile versions collected', () => {
    const itemCap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const v11Draft = {
      ...itemDraft(),
      capture_photo_id: 'cap-v11',
      recognition_profile_snapshot_json: JSON.stringify({
        client_supplier_id: 'sup-b',
        item: {
          status: 'VALID',
          profile_id: 'prof-item',
          profile_version: 11,
          profile_source: 'SUPPLIER',
          label_id: 'L2',
          sku: 'S2',
          quantity: 1,
        },
      }),
      product_results_json: JSON.stringify([
        {
          labelId: 'L2',
          internalCode: 'S2',
          quantity: 1,
          formatVersion: 'SUPPLIER',
          rawPayload: 'L2|S2|1',
        },
      ]),
    };
    const cap11 = mapPhotoToCapture({
      photo: photo('cap-v11'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: v11Draft,
      includeAssets: false,
      requireAssets: false,
    });
    const profiles = collectProfileEntries([itemCap, cap11]);
    expect(profiles.map((p) => p.profile_version).sort()).toEqual([10, 11]);
  });

  it('14. exact empty-segment raw preserved', () => {
    const raw = 'A04-R-02|04||02';
    const draft = {
      ...positionDraft(),
      product_results_json: null,
      position_snapshot_json: JSON.stringify({ rawPayload: raw, sourcePayload: raw }),
    };
    const cap = mapPhotoToCapture({
      photo: photo('cap-empty'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft,
      includeAssets: false,
      requireAssets: false,
    });
    expect(cap.recognitions.position?.raw_evidence.raw_payload).toBe(raw);
  });

  it('15. deterministic capture ordering', () => {
    const capA = mapPhotoToCapture({
      photo: { ...photo('cap-b'), stable_at: '2026-01-02T00:00:00.000Z', created_at: '2026-01-02T00:00:00.000Z' },
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: false,
      requireAssets: false,
    });
    const capB = mapPhotoToCapture({
      photo: { ...photo('cap-a'), stable_at: '2026-01-01T00:00:00.000Z', created_at: '2026-01-01T00:00:00.000Z' },
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: { ...itemDraft(), capture_photo_id: 'cap-a' },
      includeAssets: false,
      requireAssets: false,
    });
    const sorted = sortCapturesDeterministic([capA, capB]);
    expect(sorted[0]!.capture_id).toBe('cap-a');
    expect(sorted[1]!.capture_id).toBe('cap-b');
  });

  it('16. session latest selection uses finished_at', () => {
    const older = session({
      id: 'sess-old',
      finished_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
    });
    const newer = session({
      id: 'sess-new',
      finished_at: '2026-01-02T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
    });
    expect(selectLatestSession([older, newer]).id).toBe('sess-new');
  });

  it('17. large export uses sequential zip builder (bounded peak)', async () => {
    let concurrentLoads = 0;
    let peakConcurrent = 0;
    const entries = Array.from({ length: 100 }, (_, i) => ({
      path: `assets/f-${i}.bin`,
      getBytes: async () => {
        concurrentLoads += 1;
        peakConcurrent = Math.max(peakConcurrent, concurrentLoads);
        await new Promise((r) => setTimeout(r, 0));
        concurrentLoads -= 1;
        return new Uint8Array(1024);
      },
    }));
    entries.unshift({
      path: 'manifest.json',
      getBytes: async () => new TextEncoder().encode('{"ok":true}'),
    });
    const zip = await buildZipBytes(entries);
    expect(zip.byteLength).toBeGreaterThan(0);
    expect(peakConcurrent).toBeLessThanOrEqual(1);
  });

  it('parseProductResultsWithRaw keeps null labelId rows', () => {
    const rows = parseProductResultsWithRaw(
      JSON.stringify([
        { labelId: null, internalCode: 'ABC123', quantity: 5, rawPayload: '|ABC123|5' },
      ]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.labelId).toBeNull();
    expect(rows[0]?.internalCode).toBe('ABC123');
  });

  it('integrity paths cover all captures and included assets', () => {
    const cap = mapPhotoToCapture({
      photo: photo('cap-item'),
      session: session(),
      aisleId: 'aisle-1',
      aisleClientSupplierId: 'sup-b',
      draft: itemDraft(),
      includeAssets: true,
      requireAssets: false,
    });
    const withAsset = {
      ...cap,
      asset: { ...cap.asset!, included: true, path: 'assets/cap-item.jpg' },
    };
    const paths = buildExpectedIntegrityPaths({
      manifest: buildManifestWithIntegrity(
        {
          format: OFFLINE_AISLE_FORMAT,
          schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
          export_id: 'e1',
          created_at: '2026-01-01T00:00:00.000Z',
          app_version: '0.3.0',
          inventory: { id: 'inv-1', name: 'Inv', client_id: 'c1' },
          aisle: {
            id: 'aisle-1',
            name: 'A',
            origin: 'LOCAL',
            sync_status: 'LOCAL_ONLY',
            operational_status: 'local_completed',
          },
          supplier: { client_supplier_id: 'sup-b', name: 'S' },
          capture_count: 1,
          asset_count: 1,
          include_assets: true,
          completeness: 'COMPLETE',
        },
        {},
      ),
      aisle: {
        id: 'aisle-1',
        inventory_id: 'inv-1',
        client_supplier_id: 'sup-b',
        name: 'A',
        created_offline_at: null,
        completed_at: null,
        origin: 'LOCAL',
        sync_status: 'LOCAL_ONLY',
      },
      profiles: [],
      captures: [withAsset],
      captureFiles: { 'captures/cap-item.json': '{}' },
      assetHashes: { 'assets/cap-item.jpg': 'abc' },
    });
    expect(paths.has('aisle.json')).toBe(true);
    expect(paths.has('recognition/profiles.json')).toBe(true);
    expect(paths.has('captures/cap-item.json')).toBe(true);
    expect(paths.has('assets/cap-item.jpg')).toBe(true);
  });
});
