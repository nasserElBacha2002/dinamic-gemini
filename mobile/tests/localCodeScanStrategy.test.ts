import {
  LocalCodeScanStrategy,
  compareLocalVsServer,
} from '../src/features/localCodeScan/localCodeScanStrategy';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftRow,
  LocalDetectionDraftStatus,
} from '../src/database/repositories/localDetectionDraftRepository';
import type { DetectedCodeCandidate } from '../src/core/codeDetectionConsolidator';

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
      rawValueHash?: string | null;
      internalCode?: string | null;
      quantity?: number | null;
      quantityStatus?: string | null;
      detectedFormat?: string | null;
      detectedSymbology?: string | null;
      parserVersion: string;
      detectorVersion: string;
      candidateCount?: number;
      errorCode?: string | null;
      processingMs?: number | null;
      preparedAssetFingerprint: string;
      scanOwner?: string | null;
      scanGeneration?: number;
      comparisonStatus?: string | null;
    }): Promise<LocalDetectionDraftRow> {
      const existing = rows.find(
        (r) =>
          r.capture_photo_id === input.capturePhotoId &&
          r.detector_version === input.detectorVersion &&
          r.parser_version === input.parserVersion &&
          r.prepared_asset_fingerprint === input.preparedAssetFingerprint,
      );
      const gen = input.scanGeneration ?? 0;
      if (existing && gen < existing.scan_generation) {
        return existing;
      }
      const now = new Date().toISOString();
      const row: LocalDetectionDraftRow = {
        id: existing?.id ?? `draft-${rows.length + 1}`,
        capture_photo_id: input.capturePhotoId,
        capture_session_id: input.captureSessionId,
        client_file_id: input.clientFileId,
        status: input.status,
        raw_value_hash: input.rawValueHash ?? null,
        internal_code: input.internalCode ?? null,
        quantity: input.quantity ?? null,
        quantity_status: input.quantityStatus ?? null,
        detected_format: input.detectedFormat ?? null,
        detected_symbology: input.detectedSymbology ?? null,
        parser_version: input.parserVersion,
        detector_version: input.detectorVersion,
        candidate_count: input.candidateCount ?? 0,
        error_code: input.errorCode ?? null,
        processing_ms: input.processingMs ?? null,
        comparison_status: input.comparisonStatus ?? existing?.comparison_status ?? null,
        compare_result: existing?.compare_result ?? null,
        compared_at: existing?.compared_at ?? null,
        prepared_asset_fingerprint: input.preparedAssetFingerprint,
        scan_owner: input.scanOwner ?? null,
        scan_generation: gen,
        created_at: existing?.created_at ?? now,
        updated_at: now,
      };
      if (existing) {
        Object.assign(existing, row);
        return existing;
      }
      rows.push(row);
      return row;
    },
    async getByIdempotencyKey() {
      return null;
    },
    async listForSession() {
      return rows;
    },
    async listForPhoto() {
      return rows;
    },
    async listStaleScanning() {
      return [];
    },
    async recoverStaleScanning() {
      return 0;
    },
    async markCompared() {},
    async markComparisonMappingUnavailable() {},
    async deleteForSession() {},
    async deleteForPhoto() {},
    async deleteAll() {
      rows.length = 0;
    },
    async isScanInFlightForPhoto() {
      return false;
    },
  };
  return repo as unknown as LocalDetectionDraftRepository & { rows: LocalDetectionDraftRow[] };
}

describe('LocalCodeScanStrategy', () => {
  const baseInput = {
    capturePhotoId: 'photo-1',
    captureSessionId: 'session-1',
    clientFileId: 'cf-1',
    preparedUri: 'file:///tmp/prepared.jpg',
    preparedAssetFingerprint: 'sha256:abc',
  };

  it('marks NOT_APPLICABLE for INTERNAL_OCR', async () => {
    const drafts = createMemoryDrafts();
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect: async () => {
        throw new Error('should not detect');
      },
      evaluateCapability: async () => 'SUPPORTED',
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'INTERNAL_OCR',
      flagEnabled: true,
    });
    expect(status).toBe('NOT_APPLICABLE');
    expect(drafts.rows[0]?.status).toBe('NOT_APPLICABLE');
  });

  it('skips when flag disabled', async () => {
    const drafts = createMemoryDrafts();
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect: async () => [{ rawValue: 'ABC|5', symbology: 'QR_CODE' }],
      evaluateCapability: async ({ flagEnabled }) => (flagEnabled ? 'SUPPORTED' : 'DISABLED'),
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'CODE_SCAN',
      flagEnabled: false,
    });
    expect(status).toBe('NOT_APPLICABLE');
  });

  it('resolves a single valid candidate', async () => {
    const drafts = createMemoryDrafts();
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect: async () => [{ rawValue: 'ABC|5', symbology: 'QR_CODE' }],
      evaluateCapability: async () => 'SUPPORTED',
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'CODE_SCAN',
      flagEnabled: true,
    });
    expect(status).toBe('RESOLVED');
    expect(drafts.rows.at(-1)?.internal_code).toBe('ABC');
    expect(drafts.rows.at(-1)?.quantity).toBe(5);
    expect(drafts.rows.at(-1)?.raw_value_hash).toMatch(/^sha256:/);
  });

  it('marks AMBIGUOUS for distinct codes', async () => {
    const drafts = createMemoryDrafts();
    const candidates: DetectedCodeCandidate[] = [
      { rawValue: 'ABC|5', symbology: 'QR_CODE' },
      { rawValue: 'XYZ|3', symbology: 'CODE_128' },
    ];
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect: async () => candidates,
      evaluateCapability: async () => 'SUPPORTED',
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'CODE_SCAN',
      flagEnabled: true,
    });
    expect(status).toBe('AMBIGUOUS');
    expect(drafts.rows.at(-1)?.internal_code).toBeNull();
  });

  it('continues as FAILED on timeout without throwing', async () => {
    const drafts = createMemoryDrafts();
    const strategy = new LocalCodeScanStrategy({
      drafts,
      timeoutMs: 30,
      detect: async () =>
        new Promise((resolve) => {
          setTimeout(() => resolve([{ rawValue: 'ABC|5', symbology: 'QR_CODE' }]), 200);
        }),
      evaluateCapability: async () => 'SUPPORTED',
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'CODE_SCAN',
      flagEnabled: true,
    });
    expect(status).toBe('FAILED');
    expect(drafts.rows.at(-1)?.error_code).toBe('LOCAL_SCAN_TIMEOUT');
  });

  it('marks FAILED when device unsupported', async () => {
    const drafts = createMemoryDrafts();
    const strategy = new LocalCodeScanStrategy({
      drafts,
      detect: async () => [],
      evaluateCapability: async () => 'SDK_UNAVAILABLE',
    });
    const status = await strategy.execute({
      ...baseInput,
      processingMode: 'CODE_SCAN',
      flagEnabled: true,
    });
    expect(status).toBe('FAILED');
  });
});

describe('compareLocalVsServer', () => {
  it('returns NOT_COMPARABLE without reliable mapping (caller must not persist)', () => {
    expect(
      compareLocalVsServer({
        localInternalCode: 'ABC',
        localQuantity: 5,
        localStatus: 'RESOLVED',
        serverInternalCode: 'ABC',
        serverQuantity: 5,
        mappingReliable: false,
      }),
    ).toBe('NOT_COMPARABLE');
  });

  it('matches code and quantity when mapping is reliable', () => {
    expect(
      compareLocalVsServer({
        localInternalCode: 'ABC',
        localQuantity: 5,
        localStatus: 'RESOLVED',
        serverInternalCode: 'ABC',
        serverQuantity: 5,
        mappingReliable: true,
      }),
    ).toBe('MATCH_CODE_AND_QUANTITY');
  });
});
