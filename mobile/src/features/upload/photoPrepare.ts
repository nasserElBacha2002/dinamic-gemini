import * as FileSystem from 'expo-file-system';
import * as ImageManipulator from 'expo-image-manipulator';
import {
  LEGACY_JPEG_QUALITY_CONVERT,
  LEGACY_JPEG_QUALITY_RESIZE,
  targetWidthForByteBudget,
  targetWidthForMaxEdge,
  type ImagePreparationProfile,
} from '../../core/imagePreparationPolicy';
import { isAllowedImageMime, normalizeMime } from '../../shared/constants/imageFormats';
import { ensureUploadTempDirectory } from '../support/storageCleanup';

export interface PreparedUploadFile {
  readonly uri: string;
  readonly mimeType: string;
  readonly size: number;
  readonly displayName: string;
  readonly transformUri: string | null;
  /** Bytes before HEIC/resize transforms (gallery or re-stat). */
  readonly originalSize: number;
  readonly convertedFromHeic: boolean;
  readonly preparedWidth: number;
  readonly preparedHeight: number;
  readonly transformationProfile: string;
  readonly preparationProfileId: string;
  readonly preparationProfileVersion: number;
  readonly dimensionCapApplied: boolean;
  readonly formatConversionApplied: boolean;
  readonly qualityApplied: number | null;
}

export interface PrepareLimits {
  readonly maxFileSizeBytes: number;
}

/**
 * Prepare a gallery photo for multipart upload.
 *
 * Phase 1: optionally apply proactive max-edge resize and profile JPEG quality in a
 * single manipulateAsync when possible. HEIC conversion is controlled by profile.convertHeic
 * (wired from heicConvertToJpeg flag). When convertHeic is false, HEIC is uploaded as-is
 * (backend worker can normalize via pillow-heif).
 */
export async function preparePhotoForUpload(input: {
  readonly uri: string;
  readonly mimeType: string;
  readonly displayName: string;
  readonly size: number;
  readonly width: number;
  readonly height: number;
  readonly limits: PrepareLimits;
  readonly profile: ImagePreparationProfile;
  /** When false, use legacy dual qualities (0.92 convert / 0.85 resize) instead of profile.jpegQuality. */
  readonly adaptiveQualityEnabled: boolean;
}): Promise<PreparedUploadFile> {
  const mime = normalizeMime(input.mimeType);
  if (!isAllowedImageMime(mime)) {
    throw new Error(`MIME no permitido: ${mime || 'unknown'}`);
  }

  let size = input.size;
  if (!(size > 0)) {
    try {
      const info = await FileSystem.getInfoAsync(input.uri, { size: true });
      if (info.exists && typeof info.size === 'number' && info.size > 0) {
        size = info.size;
      }
    } catch {
      // fall through
    }
  }
  if (!(size > 0)) {
    throw new Error('Archivo vacío');
  }

  const originalSize = size;
  const originalWidth = input.width > 0 ? input.width : 0;
  const originalHeight = input.height > 0 ? input.height : 0;
  let uri = input.uri;
  let mimeType = mime === 'image/jpg' ? 'image/jpeg' : mime;
  let transformUri: string | null = null;
  let convertedFromHeic = false;
  let displayName = input.displayName;
  let preparedWidth = originalWidth;
  let preparedHeight = originalHeight;
  let dimensionCapApplied = false;
  let qualityApplied: number | null = null;

  const isHeic = mimeType === 'image/heic' || mimeType === 'image/heif';
  const needsHeicConvert = isHeic && input.profile.convertHeic;

  // Estimate whether dimension cap applies before transform (may refine after HEIC).
  const edgeWidth = targetWidthForMaxEdge({
    width: originalWidth,
    height: originalHeight,
    maxEdgeDimension: input.profile.maxEdgeDimension,
  });

  // Byte-budget shrink may also be needed (legacy path when over max file size).
  const byteWidth = targetWidthForByteBudget({
    width: originalWidth || 1,
    height: originalHeight || 1,
    currentBytes: size,
    maxFileSizeBytes: input.limits.maxFileSizeBytes,
  });

  const needsTransform =
    needsHeicConvert || edgeWidth != null || byteWidth != null || (isHeic && input.profile.convertHeic);

  if (!needsTransform) {
    // Passthrough: JPEG/PNG/WebP under dimension + byte limits, or HEIC when convert disabled.
    return {
      uri,
      mimeType,
      size,
      displayName,
      transformUri: null,
      originalSize,
      convertedFromHeic: false,
      preparedWidth,
      preparedHeight,
      transformationProfile: isHeic ? 'heic_passthrough' : 'passthrough',
      preparationProfileId: input.profile.profileId,
      preparationProfileVersion: input.profile.version,
      dimensionCapApplied: false,
      formatConversionApplied: false,
      qualityApplied: null,
    };
  }

  // Single manipulate pass: optional resize + JPEG encode.
  const actions: ImageManipulator.Action[] = [];
  const resizeWidth =
    edgeWidth != null && byteWidth != null
      ? Math.min(edgeWidth, byteWidth)
      : edgeWidth ?? byteWidth ?? null;
  if (resizeWidth != null && originalWidth > 0 && resizeWidth < originalWidth) {
    actions.push({ resize: { width: resizeWidth } });
    dimensionCapApplied = edgeWidth != null && (byteWidth == null || edgeWidth <= byteWidth);
  } else if (resizeWidth != null && originalWidth <= 0) {
    // Unknown width: still request resize by long-edge estimate using height if available.
    actions.push({ resize: { width: resizeWidth } });
    dimensionCapApplied = edgeWidth != null;
  }

  const quality = resolveJpegQuality({
    adaptiveQualityEnabled: input.adaptiveQualityEnabled,
    profileQuality: input.profile.jpegQuality,
    willResize: actions.length > 0,
    willConvertHeic: needsHeicConvert,
  });
  qualityApplied = quality;

  const result = await ImageManipulator.manipulateAsync(uri, actions, {
    compress: quality,
    format: ImageManipulator.SaveFormat.JPEG,
  });

  uri = await relocateTransform(result.uri);
  transformUri = uri;
  mimeType = 'image/jpeg';
  if (needsHeicConvert) {
    convertedFromHeic = true;
    displayName = displayName.replace(/\.(heic|heif)$/i, '.jpg');
  } else if (actions.length > 0 || mimeType === 'image/jpeg') {
    displayName = displayName.replace(/\.[^.]+$/, '.jpg');
  }
  if (typeof result.width === 'number' && result.width > 0) {
    preparedWidth = result.width;
  }
  if (typeof result.height === 'number' && result.height > 0) {
    preparedHeight = result.height;
  }
  const info = await FileSystem.getInfoAsync(uri);
  size = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : size;

  // Second pass only if still over byte budget after dimension cap (rare).
  if (size > input.limits.maxFileSizeBytes) {
    const secondWidth = targetWidthForByteBudget({
      width: preparedWidth > 0 ? preparedWidth : originalWidth || 1280,
      height: preparedHeight > 0 ? preparedHeight : originalHeight || 1280,
      currentBytes: size,
      maxFileSizeBytes: input.limits.maxFileSizeBytes,
    });
    if (secondWidth == null) {
      throw new Error('Archivo demasiado grande tras transformar');
    }
    const secondQuality = input.adaptiveQualityEnabled
      ? Math.max(0.75, quality - 0.05)
      : LEGACY_JPEG_QUALITY_RESIZE;
    const prev = transformUri;
    const second = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: secondWidth } }],
      { compress: secondQuality, format: ImageManipulator.SaveFormat.JPEG },
    );
    uri = await relocateTransform(second.uri);
    transformUri = uri;
    if (prev && prev !== uri) {
      await safeDelete(prev);
    }
    qualityApplied = secondQuality;
    if (typeof second.width === 'number' && second.width > 0) {
      preparedWidth = second.width;
    }
    if (typeof second.height === 'number' && second.height > 0) {
      preparedHeight = second.height;
    }
    const info2 = await FileSystem.getInfoAsync(uri);
    size = info2.exists && 'size' in info2 && typeof info2.size === 'number' ? info2.size : size;
  }

  if (size > input.limits.maxFileSizeBytes) {
    throw new Error('Archivo demasiado grande tras transformar');
  }

  const transformationProfile = buildTransformationProfileLabel({
    convertedFromHeic,
    resized: actions.length > 0 || dimensionCapApplied,
    heicPassthrough: isHeic && !needsHeicConvert,
  });

  return {
    uri,
    mimeType,
    size,
    displayName,
    transformUri,
    originalSize,
    convertedFromHeic,
    preparedWidth,
    preparedHeight,
    transformationProfile,
    preparationProfileId: input.profile.profileId,
    preparationProfileVersion: input.profile.version,
    dimensionCapApplied,
    formatConversionApplied: convertedFromHeic || actions.length > 0,
    qualityApplied,
  };
}

function resolveJpegQuality(input: {
  readonly adaptiveQualityEnabled: boolean;
  readonly profileQuality: number;
  readonly willResize: boolean;
  readonly willConvertHeic: boolean;
}): number {
  if (input.adaptiveQualityEnabled) {
    return input.profileQuality;
  }
  if (input.willResize) {
    return LEGACY_JPEG_QUALITY_RESIZE;
  }
  if (input.willConvertHeic) {
    return LEGACY_JPEG_QUALITY_CONVERT;
  }
  return LEGACY_JPEG_QUALITY_CONVERT;
}

function buildTransformationProfileLabel(input: {
  readonly convertedFromHeic: boolean;
  readonly resized: boolean;
  readonly heicPassthrough: boolean;
}): string {
  if (input.heicPassthrough) return 'heic_passthrough';
  if (input.convertedFromHeic && input.resized) return 'heic_resize_jpeg';
  if (input.convertedFromHeic) return 'heic_jpeg';
  if (input.resized) return 'resize_jpeg';
  return 'jpeg_reencode';
}

export async function cleanupTransformUri(uri: string | null | undefined): Promise<void> {
  if (!uri) {
    return;
  }
  await safeDelete(uri);
}

async function relocateTransform(sourceUri: string): Promise<string> {
  const dir = await ensureUploadTempDirectory();
  if (!dir) {
    return sourceUri;
  }
  const name = `xf-${Date.now()}-${Math.random().toString(36).slice(2, 10)}.jpg`;
  const dest = `${dir}${name}`;
  try {
    await FileSystem.copyAsync({ from: sourceUri, to: dest });
    if (sourceUri !== dest) {
      await safeDelete(sourceUri);
    }
    return dest;
  } catch {
    return sourceUri;
  }
}

async function safeDelete(uri: string): Promise<void> {
  try {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  } catch {
    // best-effort
  }
}
