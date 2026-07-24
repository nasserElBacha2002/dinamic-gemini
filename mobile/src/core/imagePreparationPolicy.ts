/**
 * Phase 1 — image preparation profiles (pure, testable).
 */

import { DEFAULT_MAX_DIMENSION_PX } from '../shared/constants/photoPrepare';
import type { NormalizedNetworkType } from '../observability/types';

export type PreparationProcessingMode = 'CODE_SCAN' | 'INTERNAL_OCR' | 'LEGACY_LLM' | 'UNKNOWN';

export type ResizeReason = 'dimension_cap' | 'byte_budget' | 'both' | 'none';

export interface UploadLimitsSnapshot {
  readonly maxFileSizeBytes: number;
}

export interface ImagePreparationContext {
  readonly processingMode: PreparationProcessingMode;
  readonly networkType: NormalizedNetworkType;
  readonly serverLimits: UploadLimitsSnapshot;
  readonly dimensionCapEnabled: boolean;
  readonly adaptiveQualityEnabled: boolean;
  readonly convertHeic: boolean;
}

export interface ImagePreparationProfile {
  readonly profileId: string;
  readonly version: number;
  readonly maxEdgeDimension: number | null;
  readonly jpegQuality: number;
  readonly minimumJpegQuality: number;
  readonly minimumEdgeDimension: number;
  readonly maxTransformPasses: number;
  readonly outputFormat: 'jpeg';
  readonly convertHeic: boolean;
}

export interface ImagePreparationPolicy {
  resolve(input: ImagePreparationContext): ImagePreparationProfile;
}

export const PREPARATION_PROFILE_VERSION = 2;

const PROFILE_CODE_SCAN = {
  profileId: 'code_scan_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  jpegQuality: 0.9,
  minimumJpegQuality: 0.86,
  minimumEdgeDimension: 1600,
  maxTransformPasses: 2,
} as const;

const PROFILE_INTERNAL_OCR = {
  profileId: 'internal_ocr_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  jpegQuality: 0.92,
  minimumJpegQuality: 0.88,
  minimumEdgeDimension: 1800,
  maxTransformPasses: 2,
} as const;

const PROFILE_LEGACY_LLM = {
  profileId: 'legacy_llm_v1',
  maxEdgeDimension: Math.min(DEFAULT_MAX_DIMENSION_PX, 2560),
  jpegQuality: 0.88,
  minimumJpegQuality: 0.8,
  minimumEdgeDimension: 1280,
  maxTransformPasses: 2,
} as const;

const PROFILE_UNKNOWN = {
  profileId: 'unknown_safe_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  jpegQuality: 0.9,
  minimumJpegQuality: 0.85,
  minimumEdgeDimension: 1600,
  maxTransformPasses: 2,
} as const;

export const LEGACY_JPEG_QUALITY_CONVERT = 0.92;
export const LEGACY_JPEG_QUALITY_RESIZE = 0.85;

export function normalizePreparationProcessingMode(raw: unknown): PreparationProcessingMode {
  const upper = String(raw ?? '')
    .trim()
    .toUpperCase();
  if (upper === 'CODE_SCAN') return 'CODE_SCAN';
  if (upper === 'INTERNAL_OCR') return 'INTERNAL_OCR';
  if (upper === 'LEGACY_LLM' || upper === 'LEGACY_LLM_TEMPORARY') return 'LEGACY_LLM';
  return 'UNKNOWN';
}

/**
 * Early capture uploads default session mode to UNKNOWN. When local CODE_SCAN is
 * opted in, still run barcode detection (do not mark NOT_APPLICABLE).
 * Explicit INTERNAL_OCR / LEGACY_LLM remain non-applicable for local barcode scan.
 */
export function resolveLocalScanProcessingMode(
  mode: PreparationProcessingMode,
  flagEnabled: boolean,
): PreparationProcessingMode {
  if (!flagEnabled) {
    return mode;
  }
  if (mode === 'UNKNOWN') {
    return 'CODE_SCAN';
  }
  return mode;
}

function baseForMode(mode: PreparationProcessingMode) {
  switch (mode) {
    case 'CODE_SCAN':
      return { ...PROFILE_CODE_SCAN };
    case 'INTERNAL_OCR':
      return { ...PROFILE_INTERNAL_OCR };
    case 'LEGACY_LLM':
      return { ...PROFILE_LEGACY_LLM };
    default:
      return { ...PROFILE_UNKNOWN };
  }
}

function applyNetworkQualityNudge(
  quality: number,
  networkType: NormalizedNetworkType,
  adaptiveQualityEnabled: boolean,
  minimumJpegQuality: number,
): number {
  if (!adaptiveQualityEnabled) {
    return quality;
  }
  if (networkType === 'cellular') {
    return Math.max(minimumJpegQuality, Math.round((quality - 0.03) * 100) / 100);
  }
  return quality;
}

export function clampJpegQuality(quality: number, minimum = 0.5): number {
  if (!Number.isFinite(quality)) {
    return LEGACY_JPEG_QUALITY_CONVERT;
  }
  return Math.min(0.98, Math.max(minimum, quality));
}

export class DefaultImagePreparationPolicy implements ImagePreparationPolicy {
  resolve(input: ImagePreparationContext): ImagePreparationProfile {
    const base = baseForMode(input.processingMode);
    const maxEdge =
      input.dimensionCapEnabled && base.maxEdgeDimension > 0 ? base.maxEdgeDimension : null;
    const jpegQuality = input.adaptiveQualityEnabled
      ? clampJpegQuality(
          applyNetworkQualityNudge(
            base.jpegQuality,
            input.networkType,
            true,
            base.minimumJpegQuality,
          ),
          base.minimumJpegQuality,
        )
      : LEGACY_JPEG_QUALITY_RESIZE;

    return {
      profileId: base.profileId,
      version: PREPARATION_PROFILE_VERSION,
      maxEdgeDimension: maxEdge,
      jpegQuality,
      minimumJpegQuality: base.minimumJpegQuality,
      minimumEdgeDimension: base.minimumEdgeDimension,
      maxTransformPasses: base.maxTransformPasses,
      outputFormat: 'jpeg',
      convertHeic: input.convertHeic,
    };
  }
}

export const defaultImagePreparationPolicy = new DefaultImagePreparationPolicy();

export function targetWidthForMaxEdge(input: {
  readonly width: number;
  readonly height: number;
  readonly maxEdgeDimension: number | null;
}): number | null {
  const w = input.width;
  const h = input.height;
  const maxEdge = input.maxEdgeDimension;
  if (!(w > 0) || !(h > 0) || maxEdge == null || !(maxEdge > 0)) {
    return null;
  }
  const longEdge = Math.max(w, h);
  if (longEdge <= maxEdge) {
    return null;
  }
  if (w >= h) {
    return maxEdge;
  }
  return Math.max(1, Math.floor((w * maxEdge) / h));
}

export function targetWidthForByteBudget(input: {
  readonly width: number;
  readonly height: number;
  readonly currentBytes: number;
  readonly maxFileSizeBytes: number;
  readonly minimumEdgeDimension: number;
}): number | null {
  if (!(input.currentBytes > input.maxFileSizeBytes) || !(input.width > 0)) {
    return null;
  }
  const scale = Math.sqrt(input.maxFileSizeBytes / input.currentBytes) * 0.95;
  const floor = Math.max(1, input.minimumEdgeDimension);
  return Math.max(floor, Math.floor(input.width * Math.min(1, scale)));
}

export function classifyResizeReason(input: {
  readonly edgeResize: boolean;
  readonly byteResize: boolean;
}): ResizeReason {
  if (input.edgeResize && input.byteResize) return 'both';
  if (input.edgeResize) return 'dimension_cap';
  if (input.byteResize) return 'byte_budget';
  return 'none';
}

export function isFormatConversion(input: {
  readonly sourceMime: string;
  readonly outputMime: string;
}): boolean {
  const src = input.sourceMime.toLowerCase();
  const out = input.outputMime.toLowerCase();
  if (src === out || (src === 'image/jpg' && out === 'image/jpeg')) {
    return false;
  }
  return src !== out;
}
