/**
 * Strict multilabel CODE_SCAN: Photo 2 / 3 / 6 fixtures + cardinality + D1-vs-legacy.
 */

import { describe, expect, it } from '@jest/globals';
import * as fs from 'fs';
import * as path from 'path';
import {
  buildOverlapScanTiles,
  mergeBarcodeHitsByRawValue,
} from '../src/core/barcodeScanMultipass';
import { consolidateCodeDetections } from '../src/core/codeDetectionConsolidator';
import { buildProductLabelPayload, parseProductLabelPayload } from '../src/core/productLabelFormat';
import { LOCAL_CODE_DETECTOR_VERSION } from '../src/features/localCodeScan/localCodeDetector';
import { buildLocalCsvExport, buildLocalCsvRows } from '../src/features/localCsv/buildLocalCsvExport';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { LocalDetectionDraftRow } from '../src/database/repositories/localDetectionDraftRepository';
import { LocalCodeScanStrategy } from '../src/features/localCodeScan/localCodeScanStrategy';
import type { DetectedCodeCandidate } from '../src/core/codeDetectionConsolidator';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftStatus,
} from '../src/database/repositories/localDetectionDraftRepository';

function checksumVectors(): {
  vectors: Array<{ name: string; tampered_payload?: string }>;
} {
  return JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, '../../contracts/product-labels/v1/checksum-vectors.json'),
      'utf8',
    ),
  ) as { vectors: Array<{ name: string; tampered_payload?: string }> };
}

function makeSession(): CaptureSessionRow {
  return {
    id: 'sess-1',
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_id: 'aisle-1',
    aisle_name: 'A1',
    status: 'active',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
  } as CaptureSessionRow;
}

function makePhoto(id: string, order: number): CapturePhotoRow {
  return {
    id,
    capture_session_id: 'sess-1',
    asset_id: `asset-${id}`,
    status: 'ready',
    sequence_number: order,
    date_added: order,
    created_at: '2026-08-10T00:00:00Z',
    client_file_id: `cf-${id}`,
  } as unknown as CapturePhotoRow;
}

function makeDraft(
  photoId: string,
  overrides: Partial<LocalDetectionDraftRow>,
): LocalDetectionDraftRow {
  return {
    id: `draft-${photoId}`,
    capture_photo_id: photoId,
    capture_session_id: 'sess-1',
    client_file_id: `cf-${photoId}`,
    status: 'RESOLVED',
    raw_value_hash: null,
    internal_code: null,
    quantity: null,
    quantity_status: null,
    detected_format: null,
    detected_symbology: null,
    parser_version: '1',
    detector_version: '1',
    candidate_count: 1,
    error_code: null,
    processing_ms: 1,
    comparison_status: 'PENDING',
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
    label_id: null,
    product_results_json: null,
    rejections_json: null,
    position_detected: 0,
    detected_at: '2026-08-10T00:00:00Z',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    ...overrides,
  };
}

function createMemoryDrafts(): LocalDetectionDraftRepository & {
  rows: LocalDetectionDraftRow[];
} {
  const rows: LocalDetectionDraftRow[] = [];
  const repo = {
    rows,
    async upsertDraft(input: {
      capturePhotoId: string;
      captureSessionId: string;
      clientFileId: string | null;
      status: LocalDetectionDraftStatus;
      parserVersion: string;
      detectorVersion: string;
      preparedAssetFingerprint: string;
      internalCode?: string | null;
      quantity?: number | null;
      labelId?: string | null;
      productResultsJson?: string | null;
      rejectionsJson?: string | null;
      positionDetected?: boolean | null;
      errorCode?: string | null;
      candidateCount?: number;
      scanGeneration?: number;
      [key: string]: unknown;
    }): Promise<LocalDetectionDraftRow> {
      const now = new Date().toISOString();
      const row = makeDraft(input.capturePhotoId, {
        status: input.status,
        internal_code: (input.internalCode as string | null) ?? null,
        quantity: (input.quantity as number | null) ?? null,
        label_id: (input.labelId as string | null) ?? null,
        product_results_json: (input.productResultsJson as string | null) ?? null,
        rejections_json: (input.rejectionsJson as string | null) ?? null,
        position_detected: input.positionDetected ? 1 : 0,
        error_code: (input.errorCode as string | null) ?? null,
        candidate_count: (input.candidateCount as number) ?? 0,
        scan_generation: (input.scanGeneration as number) ?? 0,
        detector_version: input.detectorVersion,
        parser_version: input.parserVersion,
        prepared_asset_fingerprint: input.preparedAssetFingerprint,
        updated_at: now,
      });
      const idx = rows.findIndex((r) => r.capture_photo_id === input.capturePhotoId);
      if (idx >= 0) {
        rows[idx] = row;
      } else {
        rows.push(row);
      }
      return row;
    },
    async listForSession() {
      return rows;
    },
    async listForPhoto() {
      return rows;
    },
    async recoverStaleScanning() {
      return 0;
    },
  };
  return repo as unknown as LocalDetectionDraftRepository & { rows: LocalDetectionDraftRow[] };
}

describe('strict multilabel consolidator cardinality', () => {
  it('1 valid → 1', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU1',
      quantity: 1,
    });
    const r = consolidateCodeDetections([{ rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 }]);
    expect(r.productResults).toHaveLength(1);
    expect(r.d1Mode).toBe(true);
  });

  it('2 valid → 2', () => {
    const a = buildProductLabelPayload({
      labelId: '6YD0S6WVMM',
      internalCode: '232424090',
      quantity: 1000,
    });
    const b = buildProductLabelPayload({
      labelId: '6FYR11RPXS',
      internalCode: '232424025',
      quantity: 1100,
    });
    const r = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
    ]);
    expect(r.status).toBe('RESOLVED_MULTI');
    expect(r.productResults).toHaveLength(2);
    expect(r.productResults.map((p) => p.labelId).sort()).toEqual(
      ['6FYR11RPXS', '6YD0S6WVMM'].sort(),
    );
  });

  it('5 valid → 5', () => {
    const ids = ['A1B2C3D4E5', 'FGHJKMNPQR', 'STVWXYZ234', '456789ABCD', 'EFGHJKMNPQ'];
    const candidates = ids.map((labelId, i) => ({
      rawValue: buildProductLabelPayload({
        labelId,
        internalCode: `SKU${i}`,
        quantity: i + 1,
      }),
      symbology: 'QR_CODE',
      detectionIndex: i,
    }));
    expect(consolidateCodeDetections(candidates).productResults).toHaveLength(5);
  });

  it('Photo 2: 2 valid + 1 invalid + legacy → 2 products, 1+ rejection', () => {
    const a = buildProductLabelPayload({
      labelId: 'VY1FNYHF94',
      internalCode: '90808090909',
      quantity: 1000,
    });
    const b = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU_B',
      quantity: 50,
    });
    const tampered = checksumVectors().vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    const r = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
      {
        rawValue: tampered.tampered_payload as string,
        symbology: 'QR_CODE',
        detectionIndex: 2,
      },
      { rawValue: '5949604043|42142', symbology: 'CODE_128', detectionIndex: 3 },
    ]);
    expect(r.d1Mode).toBe(true);
    expect(r.productResults).toHaveLength(2);
    expect(r.rejections.length).toBeGreaterThanOrEqual(1);
    expect(r.productResults.every((p) => p.labelId)).toBe(true);
  });

  it('Photo 3: position + invalid D1 + legacy → 0 products, rejection, d1Mode', () => {
    const tampered = checksumVectors().vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    const pos = JSON.stringify({
      type: 'DINAMIC_POSITION',
      version: 2,
      label_id: 'pos_ej3uISIYC63aMKeO',
      pallet: '04',
      side: 'RIGHT',
      level: 1,
      marker_index: 1,
      marker_total: 2,
    });
    const r = consolidateCodeDetections([
      { rawValue: pos, symbology: 'QR_CODE', detectionIndex: 0 },
      {
        rawValue: tampered.tampered_payload as string,
        symbology: 'QR_CODE',
        detectionIndex: 1,
      },
      { rawValue: '5949604043|42142', symbology: 'CODE_128', detectionIndex: 2 },
    ]);
    expect(r.d1Mode).toBe(true);
    expect(r.productResults).toHaveLength(0);
    expect(r.rejections.length).toBeGreaterThanOrEqual(1);
    expect(r.positionRawPayload).toBe(pos);
    expect(r.warnings).toContain('D1_CANDIDATES_FAILED');
    expect(r.internalCode).toBeNull();
  });

  it('Photo 6 exact label ids', () => {
    const a = buildProductLabelPayload({
      labelId: '6YD0S6WVMM',
      internalCode: '232424090',
      quantity: 1000,
    });
    const b = buildProductLabelPayload({
      labelId: '6FYR11RPXS',
      internalCode: '232424025',
      quantity: 1100,
    });
    // Plus legacy Code128 companions — must not collapse or add third product.
    const r = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: '232424090|1000', symbology: 'CODE_128', detectionIndex: 1 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 2 },
      { rawValue: '232424025|1100', symbology: 'CODE_128', detectionIndex: 3 },
    ]);
    expect(r.productResults).toHaveLength(2);
    expect(r.productResults.find((p) => p.labelId === '6YD0S6WVMM')?.quantity).toBe(1000);
    expect(r.productResults.find((p) => p.labelId === '6FYR11RPXS')?.quantity).toBe(1100);
  });

  it('D1| grammar mismatch is MALFORMED not NOT_OUR_FORMAT', () => {
    const parsed = parseProductLabelPayload('D1|BAD|X|1|Z');
    expect(parsed.status).toBe('MALFORMED');
    expect(consolidateCodeDetections([
      { rawValue: 'D1|BAD|X|1|Z', symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: 'SKU|99', symbology: 'CODE_128', detectionIndex: 1 },
    ]).productResults).toHaveLength(0);
  });

  it('same label duplicate → 1; same SKU different labels → 2', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SAME',
      quantity: 1,
    });
    const b = buildProductLabelPayload({
      labelId: 'FGHJKMNPQR',
      internalCode: 'SAME',
      quantity: 2,
    });
    expect(
      consolidateCodeDetections([
        { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
        { rawValue: a, symbology: 'QR_CODE', detectionIndex: 1 },
      ]).productResults,
    ).toHaveLength(1);
    expect(
      consolidateCodeDetections([
        { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
        { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
      ]).productResults,
    ).toHaveLength(2);
  });
});

describe('strict multilabel CSV + strategy', () => {
  it('CSV expands product_results_json to 2 rows; rejects do not create product rows', async () => {
    const draft = makeDraft('photo-6', {
      product_results_json: JSON.stringify([
        { labelId: '6YD0S6WVMM', internalCode: '232424090', quantity: 1000 },
        { labelId: '6FYR11RPXS', internalCode: '232424025', quantity: 1100 },
      ]),
      rejections_json: JSON.stringify([
        { labelId: null, validationStatus: 'D1_CHECKSUM_FAILED', reason: 'checksum mismatch' },
      ]),
      label_id: '6YD0S6WVMM',
      internal_code: '232424090',
      quantity: 1000,
    });
    const rows = buildLocalCsvRows({
      session: makeSession(),
      photos: [makePhoto('photo-6', 6)],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev',
      companyId: null,
      clientId: 'c',
    });
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.capture_photo_id === 'photo-6')).toBe(true);
    const built = await buildLocalCsvExport({
      session: makeSession(),
      photos: [makePhoto('photo-6', 6)],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev',
      companyId: null,
      clientId: 'c',
    });
    expect(built.productResultCount).toBe(2);
    expect(built.rejectedDetectionCount).toBe(1);
    expect(built.rowCount).toBe(2);
  });

  it('Photo 3 CSV: no legacy revival when D1_CANDIDATES_FAILED + scalar code present', () => {
    const draft = makeDraft('photo-3', {
      status: 'INVALID',
      internal_code: '5949604043',
      quantity: 42142,
      label_id: null,
      product_results_json: null,
      rejections_json: JSON.stringify([
        {
          labelId: 'TAMPERED1',
          validationStatus: 'D1_CHECKSUM_FAILED',
          reason: 'checksum mismatch',
        },
      ]),
      error_code: 'D1_CANDIDATES_FAILED',
      position_detected: 1,
      position_snapshot_json: JSON.stringify({
        labelId: 'pos_x',
        positionLabelId: 'pos_x',
        displayName: 'Pallet 04',
        canonicalKey: '04|RIGHT|1|1|2',
        pallet: '04',
        side: 'RIGHT',
        level: 1,
        markerIndex: 1,
        markerTotal: 2,
        formattedMarker: '01/02',
        rawPayload: '{"type":"DINAMIC_POSITION","label_id":"pos_x"}',
        sourcePayload: '{"type":"DINAMIC_POSITION","label_id":"pos_x"}',
        validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
      }),
    });
    const rows = buildLocalCsvRows({
      session: makeSession(),
      photos: [makePhoto('photo-3', 3)],
      drafts: [draft],
      confirmed: [],
      deviceId: 'dev',
      companyId: null,
      clientId: 'c',
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]!.source).toBe('LOCAL_POSITION_LABEL');
    expect(rows[0]!.internal_code).toBe('');
    expect(rows[0]!.label_id).toBe('');
  });

  it('strategy stores N products + rejections_json for Photo 2 fixture', async () => {
    const drafts = createMemoryDrafts();
    const a = buildProductLabelPayload({
      labelId: 'VY1FNYHF94',
      internalCode: '90808090909',
      quantity: 1000,
    });
    const b = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU_B',
      quantity: 50,
    });
    const tampered = checksumVectors().vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    const detect = async (): Promise<DetectedCodeCandidate[]> => [
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
      {
        rawValue: tampered.tampered_payload as string,
        symbology: 'QR_CODE',
        detectionIndex: 2,
      },
      { rawValue: 'LEGACY|999', symbology: 'CODE_128', detectionIndex: 3 },
    ];
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect,
      evaluateCapability: async () => 'SUPPORTED',
    });
    const status = await strategy.execute({
      capturePhotoId: 'photo-2',
      captureSessionId: 'sess-1',
      clientFileId: 'cf-2',
      preparedUri: 'file:///tmp/x.jpg',
      preparedAssetFingerprint: 'fp',
      processingMode: 'CODE_SCAN',
      flagEnabled: true,
    });
    expect(status).toBe('RESOLVED');
    const row = drafts.rows[0]!;
    const products = JSON.parse(row.product_results_json!) as unknown[];
    expect(products).toHaveLength(2);
    const rejections = JSON.parse(row.rejections_json!) as unknown[];
    expect(rejections.length).toBeGreaterThanOrEqual(1);
    expect(row.internal_code).not.toBe('LEGACY');
  });
});

describe('ML Kit multipass merge (device root cause guard)', () => {
  it('exposes multipass detector version for re-scan', () => {
    expect(LOCAL_CODE_DETECTOR_VERSION).toContain('multipass');
  });

  it('3x3 tiles cover full image and overlap', () => {
    const tiles = buildOverlapScanTiles({ width: 1200, height: 1600, grid: 3, overlapFraction: 0.2 });
    expect(tiles).toHaveLength(9);
    const leftEdge = tiles.filter((t) => t.left === 0);
    const topEdge = tiles.filter((t) => t.top === 0);
    expect(leftEdge.length).toBeGreaterThanOrEqual(3);
    expect(topEdge.length).toBeGreaterThanOrEqual(3);
    const maxRight = Math.max(...tiles.map((t) => t.left + t.width));
    const maxBottom = Math.max(...tiles.map((t) => t.top + t.height));
    expect(maxRight).toBe(1200);
    expect(maxBottom).toBe(1600);
  });

  it('merges full-pass + tile-pass like Photo 6 (2 D1 QRs)', () => {
    const a = buildProductLabelPayload({
      labelId: '6YD0S6WVMM',
      internalCode: '232424090',
      quantity: 1000,
    });
    const b = buildProductLabelPayload({
      labelId: '6FYR11RPXS',
      internalCode: '232424025',
      quantity: 1100,
    });
    // Device before fix: full frame returned only A.
    const merged = mergeBarcodeHitsByRawValue([
      [{ rawValue: a, format: 'QR_CODE' }],
      [{ rawValue: a, format: 'QR_CODE' }, { rawValue: b, format: 'QR_CODE' }],
    ]);
    expect(merged).toHaveLength(2);
    const consolidated = consolidateCodeDetections(
      merged.map((m, i) => ({
        rawValue: m.rawValue,
        symbology: m.format,
        detectionIndex: i,
      })),
    );
    expect(consolidated.productResults).toHaveLength(2);
  });
});
