/**
 * Phase 1 — image preparation profiles (pure, testable).
 * Defaults are conservative for remote CODE_SCAN / OCR / visual pipelines.
 * Not device-specific (no S10+ hardcoding).
 */

import { DEFAULT_MAX_DIMENSION_PX } from '../shared/constants/photoPrepare';
import type { NormalizedNetworkType } from '../observability/types';

export type PreparationProcessingMode = 'CODE_SCAN' | 'INTERNAL_OCR' | 'LEGACY_LLM' | 'UNKNOWN';

export interface UploadLimitsSnapshot {
  readonly maxFileSizeBytes: number;
}

export interface ImagePreparationContext {
  readonly processingMode: PreparationProcessingMode;
  readonly originalWidth?: number | null;
  readonly originalHeight?: number | null;
  readonly originalBytes: number;
  readonly networkType: NormalizedNetworkType;
  readonly serverLimits: UploadLimitsSnapshot;
  /** When false, proactive dimension cap is disabled (legacy: resize only if over byte limit). */
  readonly dimensionCapEnabled: boolean;
  /** When false, use legacy fixed JPEG qualities instead of profile quality. */
  readonly adaptiveQualityEnabled: boolean;
}

export interface ImagePreparationProfile {
  readonly profileId: string;
  readonly version: number;
  readonly maxEdgeDimension: number | null;
  readonly jpegQuality: number;
  readonly outputFormat: 'jpeg';
  readonly convertHeic: boolean;
}

export interface ImagePreparationPolicy {
  resolve(input: ImagePreparationContext & { readonly convertHeic: boolean }): ImagePreparationProfile;
}

/** Profile catalog — version bumped when defaults change meaningfully. */
export const PREPARATION_PROFILE_VERSION = 1;

const PROFILE_CODE_SCAN = {
  profileId: 'code_scan_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  /** Preserve barcode modules; mild compression. */
  jpegQuality: 0.9,
} as const;

const PROFILE_INTERNAL_OCR = {
  profileId: 'internal_ocr_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  /** Prefer sharpness for small glyphs. */
  jpegQuality: 0.92,
} as const;

const PROFILE_LEGACY_LLM = {
  profileId: 'legacy_llm_v1',
  maxEdgeDimension: Math.min(DEFAULT_MAX_DIMENSION_PX, 2560),
  jpegQuality: 0.88,
} as const;

const PROFILE_UNKNOWN = {
  profileId: 'unknown_safe_v1',
  maxEdgeDimension: DEFAULT_MAX_DIMENSION_PX,
  jpegQuality: 0.9,
} as const;

/** Legacy qualities when adaptive quality flag is off. */
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

function baseForMode(mode: PreparationProcessingMode): {
  profileId: string;
  maxEdgeDimension: number;
  jpegQuality: number;
} {
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

/**
 * Mild network nudge only when adaptive quality is enabled:
 * cellular may use slightly lower quality within safe bounds (never below 0.82).
 */
function applyNetworkQualityNudge(
  quality: number,
  networkType: NormalizedNetworkType,
  adaptiveQualityEnabled: boolean,
): number {
  if (!adaptiveQualityEnabled) {
    return quality;
  }
  if (networkType === 'cellular') {
    return Math.max(0.82, Math.round((quality - 0.03) * 100) / 100);
  }
  return quality;
}

export function clampJpegQuality(quality: number): number {
  if (!Number.isFinite(quality)) {
    return LEGACY_JPEG_QUALITY_CONVERT;
  }
  return Math.min(0.98, Math.max(0.5, quality));
}

export class DefaultImagePreparationPolicy implements ImagePreparationPolicy {
  resolve(
    input: ImagePreparationContext & { readonly convertHeic: boolean },
  ): ImagePreparationProfile {
    const base = baseForMode(input.processingMode);
    const maxEdge =
      input.dimensionCapEnabled && base.maxEdgeDimension > 0 ? base.maxEdgeDimension : null;
    const jpegQuality = input.adaptiveQualityEnabled
      ? clampJpegQuality(
          applyNetworkQualityNudge(base.jpegQuality, input.networkType, true),
        )
      : LEGACY_JPEG_QUALITY_RESIZE;

    return {
      profileId: base.profileId,
      version: PREPARATION_PROFILE_VERSION,
      maxEdgeDimension: maxEdge,
      jpegQuality,
      outputFormat: 'jpeg',
      convertHeic: input.convertHeic,
    };
  }
}

export const defaultImagePreparationPolicy = new DefaultImagePreparationPolicy();

/**
 * Target width for ImageManipulator resize when capping the long edge.
 * Never upscales. Returns null when no resize needed.
 */
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
  // Height is long edge: scale width proportionally.
  return Math.max(1, Math.floor((w * maxEdge) / h));
}

/**
 * Additional shrink when prepared bytes would still exceed server max file size.
 * Uses sqrt(budget/size) heuristic (legacy), floored at 640px width.
 */
export function targetWidthForByteBudget(input: {
  readonly width: number;
  readonly height: number;
  readonly currentBytes: number;
  readonly maxFileSizeBytes: number;
}): number | null {
  if (!(input.currentBytes > input.maxFileSizeBytes) || !(input.width > 0)) {
    return null;
  }
  const scale = Math.sqrt(input.maxFileSizeBytes / input.currentBytes) * 0.95;
  return Math.max(640, Math.floor(input.width * Math.min(1, scale)));
}
