import {
  DefaultImagePreparationPolicy,
  LEGACY_JPEG_QUALITY_RESIZE,
  PREPARATION_PROFILE_VERSION,
  classifyResizeReason,
  isFormatConversion,
  normalizePreparationProcessingMode,
  targetWidthForByteBudget,
  targetWidthForMaxEdge,
} from '../src/core/imagePreparationPolicy';
import {
  DefaultUploadConcurrencyPolicy,
  UPLOAD_CONCURRENCY_CELLULAR,
  UPLOAD_CONCURRENCY_LEGACY_CAP,
  UPLOAD_CONCURRENCY_WIFI_ETHERNET,
} from '../src/core/uploadConcurrencyPolicy';
import { UploadSlotGate, prepareAllowance } from '../src/core/uploadSlotGate';
import { DEFAULT_MAX_DIMENSION_PX } from '../src/shared/constants/photoPrepare';

describe('imagePreparationPolicy', () => {
  const policy = new DefaultImagePreparationPolicy();
  const baseCtx = {
    networkType: 'wifi' as const,
    serverLimits: { maxFileSizeBytes: 12_000_000 },
    convertHeic: true,
  };

  it('selects CODE_SCAN profile with dimension cap and mins', () => {
    const profile = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    expect(profile.profileId).toBe('code_scan_v1');
    expect(profile.version).toBe(PREPARATION_PROFILE_VERSION);
    expect(profile.maxEdgeDimension).toBe(DEFAULT_MAX_DIMENSION_PX);
    expect(profile.jpegQuality).toBeGreaterThanOrEqual(0.85);
    expect(profile.minimumJpegQuality).toBeGreaterThanOrEqual(0.8);
    expect(profile.minimumEdgeDimension).toBeGreaterThanOrEqual(1600);
    expect(profile.maxTransformPasses).toBe(2);
    expect(profile.convertHeic).toBe(true);
    expect(profile.outputFormat).toBe('jpeg');
  });

  it('selects INTERNAL_OCR with higher quality bias and stricter mins', () => {
    const ocr = policy.resolve({
      ...baseCtx,
      processingMode: 'INTERNAL_OCR',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    const scan = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    expect(ocr.profileId).toBe('internal_ocr_v1');
    expect(ocr.jpegQuality).toBeGreaterThanOrEqual(scan.jpegQuality);
    expect(ocr.minimumJpegQuality).toBeGreaterThanOrEqual(scan.minimumJpegQuality);
    expect(ocr.minimumEdgeDimension).toBeGreaterThanOrEqual(scan.minimumEdgeDimension);
  });

  it('selects LEGACY_LLM with smaller edge', () => {
    const profile = policy.resolve({
      ...baseCtx,
      processingMode: 'LEGACY_LLM',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    expect(profile.profileId).toBe('legacy_llm_v1');
    expect(profile.maxEdgeDimension).toBeLessThanOrEqual(DEFAULT_MAX_DIMENSION_PX);
  });

  it('falls back safely for unknown mode', () => {
    expect(normalizePreparationProcessingMode('weird')).toBe('UNKNOWN');
    const profile = policy.resolve({
      ...baseCtx,
      processingMode: 'UNKNOWN',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    expect(profile.profileId).toBe('unknown_safe_v1');
    expect(profile.maxEdgeDimension).toBe(DEFAULT_MAX_DIMENSION_PX);
  });

  it('disables dimension cap when flag off', () => {
    const profile = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      dimensionCapEnabled: false,
      adaptiveQualityEnabled: true,
    });
    expect(profile.maxEdgeDimension).toBeNull();
  });

  it('uses legacy quality when adaptive quality off', () => {
    const profile = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: false,
    });
    expect(profile.jpegQuality).toBe(LEGACY_JPEG_QUALITY_RESIZE);
  });

  it('does not upscale and preserves aspect for max edge', () => {
    expect(
      targetWidthForMaxEdge({ width: 2000, height: 1500, maxEdgeDimension: 3000 }),
    ).toBeNull();
    expect(
      targetWidthForMaxEdge({ width: 4000, height: 3000, maxEdgeDimension: 3000 }),
    ).toBe(3000);
    expect(
      targetWidthForMaxEdge({ width: 3000, height: 4000, maxEdgeDimension: 3000 }),
    ).toBe(2250);
  });

  it('computes byte-budget width respecting minimum edge', () => {
    expect(
      targetWidthForByteBudget({
        width: 4000,
        height: 3000,
        currentBytes: 1_000_000,
        maxFileSizeBytes: 5_000_000,
        minimumEdgeDimension: 1600,
      }),
    ).toBeNull();
    const w = targetWidthForByteBudget({
      width: 4000,
      height: 3000,
      currentBytes: 20_000_000,
      maxFileSizeBytes: 5_000_000,
      minimumEdgeDimension: 1600,
    });
    expect(w).not.toBeNull();
    expect(w!).toBeGreaterThanOrEqual(1600);
    expect(w!).toBeLessThan(4000);
  });

  it('classifies resize_reason and format conversion', () => {
    expect(classifyResizeReason({ edgeResize: false, byteResize: false })).toBe('none');
    expect(classifyResizeReason({ edgeResize: true, byteResize: false })).toBe('dimension_cap');
    expect(classifyResizeReason({ edgeResize: false, byteResize: true })).toBe('byte_budget');
    expect(classifyResizeReason({ edgeResize: true, byteResize: true })).toBe('both');
    expect(isFormatConversion({ sourceMime: 'image/jpeg', outputMime: 'image/jpeg' })).toBe(false);
    expect(isFormatConversion({ sourceMime: 'image/png', outputMime: 'image/jpeg' })).toBe(true);
    expect(isFormatConversion({ sourceMime: 'image/heic', outputMime: 'image/jpeg' })).toBe(true);
  });

  it('nudges cellular quality when adaptive without going below minimum', () => {
    const wifi = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      networkType: 'wifi',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    const cell = policy.resolve({
      ...baseCtx,
      processingMode: 'CODE_SCAN',
      networkType: 'cellular',
      dimensionCapEnabled: true,
      adaptiveQualityEnabled: true,
    });
    expect(cell.jpegQuality).toBeLessThanOrEqual(wifi.jpegQuality);
    expect(cell.jpegQuality).toBeGreaterThanOrEqual(cell.minimumJpegQuality);
  });
});

describe('uploadConcurrencyPolicy', () => {
  const policy = new DefaultUploadConcurrencyPolicy();

  it('returns 0 when offline', () => {
    expect(
      policy.resolve({
        networkType: 'offline',
        serverConcurrency: 4,
        adaptiveConcurrencyEnabled: true,
      }),
    ).toBe(0);
  });

  it('caps to legacy 2 when adaptive off', () => {
    expect(
      policy.resolve({
        networkType: 'wifi',
        serverConcurrency: 8,
        adaptiveConcurrencyEnabled: false,
      }),
    ).toBe(UPLOAD_CONCURRENCY_LEGACY_CAP);
  });

  it('uses wifi/ethernet vs cellular when adaptive on', () => {
    expect(
      policy.resolve({
        networkType: 'wifi',
        serverConcurrency: 8,
        adaptiveConcurrencyEnabled: true,
      }),
    ).toBe(UPLOAD_CONCURRENCY_WIFI_ETHERNET);
    expect(
      policy.resolve({
        networkType: 'cellular',
        serverConcurrency: 8,
        adaptiveConcurrencyEnabled: true,
      }),
    ).toBe(UPLOAD_CONCURRENCY_CELLULAR);
  });

  it('never exceeds server advisory or absolute max', () => {
    expect(
      policy.resolve({
        networkType: 'wifi',
        serverConcurrency: 1,
        adaptiveConcurrencyEnabled: true,
      }),
    ).toBe(1);
    expect(
      policy.resolve({
        networkType: 'wifi',
        serverConcurrency: 99,
        adaptiveConcurrencyEnabled: true,
        absoluteMax: 2,
      }),
    ).toBe(2);
  });
});

describe('UploadSlotGate + prepareAllowance', () => {
  it('never exceeds limit and releases exactly once per acquire', () => {
    const gate = new UploadSlotGate();
    expect(gate.tryAcquire(2)).toBe(true);
    expect(gate.tryAcquire(2)).toBe(true);
    expect(gate.tryAcquire(2)).toBe(false);
    expect(gate.activeCount).toBe(2);
    gate.release();
    expect(gate.activeCount).toBe(1);
    expect(gate.tryAcquire(2)).toBe(true);
    expect(gate.activeCount).toBe(2);
    gate.release();
    gate.release();
    expect(gate.activeCount).toBe(0);
    gate.release();
    expect(gate.activeCount).toBe(0);
  });

  it('limits prepare headroom when uploads are saturated', () => {
    expect(
      prepareAllowance({
        preparedPending: 12,
        freeUploadSlots: 0,
        maxFilesPerBatch: 10,
        maxPreparedPending: 12,
      }),
    ).toBe(0);
    expect(
      prepareAllowance({
        preparedPending: 10,
        freeUploadSlots: 0,
        maxFilesPerBatch: 10,
        maxPreparedPending: 12,
      }),
    ).toBe(2);
  });

  it('caps prepare by free slots × batch size when uploads have capacity', () => {
    expect(
      prepareAllowance({
        preparedPending: 0,
        freeUploadSlots: 1,
        maxFilesPerBatch: 5,
        maxPreparedPending: 12,
      }),
    ).toBe(5);
    expect(
      prepareAllowance({
        preparedPending: 0,
        freeUploadSlots: 3,
        maxFilesPerBatch: 10,
        maxPreparedPending: 12,
      }),
    ).toBe(12);
  });
});
