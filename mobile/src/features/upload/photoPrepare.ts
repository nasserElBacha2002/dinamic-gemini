import * as FileSystem from 'expo-file-system';
import * as ImageManipulator from 'expo-image-manipulator';
import {
  LEGACY_JPEG_QUALITY_CONVERT,
  LEGACY_JPEG_QUALITY_RESIZE,
  classifyResizeReason,
  isFormatConversion,
  targetWidthForByteBudget,
  targetWidthForMaxEdge,
  type ImagePreparationProfile,
  type ResizeReason,
} from '../../core/imagePreparationPolicy';
import { isAllowedImageMime, normalizeMime } from '../../shared/constants/imageFormats';
import { ensureUploadTempDirectory } from '../support/storageCleanup';

export class PrepareFileTooLargeError extends Error {
  readonly code = 'PREPARE_FILE_TOO_LARGE';
  constructor(message = 'Archivo demasiado grande tras transformar') {
    super(message);
    this.name = 'PrepareFileTooLargeError';
  }
}

export interface PreparedUploadFile {
  readonly uri: string;
  readonly mimeType: string;
  readonly size: number;
  readonly displayName: string;
  readonly transformUri: string | null;
  readonly originalSize: number;
  readonly convertedFromHeic: boolean;
  readonly preparedWidth: number;
  readonly preparedHeight: number;
  readonly transformationProfile: string;
  readonly preparationProfileId: string;
  readonly preparationProfileVersion: number;
  readonly resizeApplied: boolean;
  readonly reencodeApplied: boolean;
  readonly formatConversionApplied: boolean;
  readonly resizeReason: ResizeReason;
  readonly qualityApplied: number | null;
}

export interface PrepareLimits {
  readonly maxFileSizeBytes: number;
}

export async function preparePhotoForUpload(input: {
  readonly uri: string;
  readonly mimeType: string;
  readonly displayName: string;
  readonly size: number;
  readonly width: number;
  readonly height: number;
  readonly limits: PrepareLimits;
  readonly profile: ImagePreparationProfile;
  readonly adaptiveQualityEnabled: boolean;
}): Promise<PreparedUploadFile> {
  const sourceMime = normalizeMime(input.mimeType);
  if (!isAllowedImageMime(sourceMime)) {
    throw new Error(`MIME no permitido: ${sourceMime || 'unknown'}`);
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
  let mimeType = sourceMime === 'image/jpg' ? 'image/jpeg' : sourceMime;
  let transformUri: string | null = null;
  let convertedFromHeic = false;
  let displayName = input.displayName;
  let preparedWidth = originalWidth;
  let preparedHeight = originalHeight;
  let qualityApplied: number | null = null;
  let transformPasses = 0;

  const isHeic = mimeType === 'image/heic' || mimeType === 'image/heif';
  const needsHeicConvert = isHeic && input.profile.convertHeic;

  const edgeWidth = targetWidthForMaxEdge({
    width: originalWidth,
    height: originalHeight,
    maxEdgeDimension: input.profile.maxEdgeDimension,
  });
  const byteWidth = targetWidthForByteBudget({
    width: originalWidth || 1,
    height: originalHeight || 1,
    currentBytes: size,
    maxFileSizeBytes: input.limits.maxFileSizeBytes,
    minimumEdgeDimension: input.profile.minimumEdgeDimension,
  });

  const needsTransform = needsHeicConvert || edgeWidth != null || byteWidth != null;

  if (!needsTransform) {
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
      resizeApplied: false,
      reencodeApplied: false,
      formatConversionApplied: false,
      resizeReason: 'none',
      qualityApplied: null,
    };
  }

  const actions: ImageManipulator.Action[] = [];
  const resizeWidth =
    edgeWidth != null && byteWidth != null
      ? Math.min(edgeWidth, byteWidth)
      : edgeWidth ?? byteWidth ?? null;
  const edgeResize = edgeWidth != null;
  const byteResize = byteWidth != null;
  if (resizeWidth != null && (originalWidth <= 0 || resizeWidth < originalWidth)) {
    actions.push({ resize: { width: resizeWidth } });
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
  transformPasses += 1;

  uri = await relocateTransform(result.uri);
  transformUri = uri;
  mimeType = 'image/jpeg';
  if (needsHeicConvert) {
    convertedFromHeic = true;
    displayName = displayName.replace(/\.(heic|heif)$/i, '.jpg');
  } else {
    displayName = displayName.replace(/\.[^.]+$/, '.jpg');
  }
  if (typeof result.width === 'number' && result.width > 0) preparedWidth = result.width;
  if (typeof result.height === 'number' && result.height > 0) preparedHeight = result.height;
  const info = await FileSystem.getInfoAsync(uri);
  size = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : size;

  if (size > input.limits.maxFileSizeBytes) {
    if (transformPasses >= input.profile.maxTransformPasses) {
      throw new PrepareFileTooLargeError();
    }
    const secondWidth = targetWidthForByteBudget({
      width: preparedWidth > 0 ? preparedWidth : originalWidth || input.profile.minimumEdgeDimension,
      height: preparedHeight > 0 ? preparedHeight : originalHeight || input.profile.minimumEdgeDimension,
      currentBytes: size,
      maxFileSizeBytes: input.limits.maxFileSizeBytes,
      minimumEdgeDimension: input.profile.minimumEdgeDimension,
    });
    if (secondWidth == null) {
      throw new PrepareFileTooLargeError();
    }
    const longEdgeAfter =
      preparedWidth > 0 && preparedHeight > 0 ? Math.max(preparedWidth, preparedHeight) : secondWidth;
    if (longEdgeAfter < input.profile.minimumEdgeDimension && secondWidth < input.profile.minimumEdgeDimension) {
      throw new PrepareFileTooLargeError('No se puede reducir más sin violar mínimos del perfil.');
    }
    const secondQuality = input.adaptiveQualityEnabled
      ? Math.max(input.profile.minimumJpegQuality, quality - 0.04)
      : LEGACY_JPEG_QUALITY_RESIZE;
    if (secondQuality < input.profile.minimumJpegQuality && input.adaptiveQualityEnabled) {
      throw new PrepareFileTooLargeError('Calidad mínima del perfil insuficiente para el límite de bytes.');
    }
    const prev = transformUri;
    const second = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: secondWidth } }],
      { compress: secondQuality, format: ImageManipulator.SaveFormat.JPEG },
    );
    transformPasses += 1;
    uri = await relocateTransform(second.uri);
    transformUri = uri;
    if (prev && prev !== uri) await safeDelete(prev);
    qualityApplied = secondQuality;
    if (typeof second.width === 'number' && second.width > 0) preparedWidth = second.width;
    if (typeof second.height === 'number' && second.height > 0) preparedHeight = second.height;
    const info2 = await FileSystem.getInfoAsync(uri);
    size = info2.exists && 'size' in info2 && typeof info2.size === 'number' ? info2.size : size;
  }

  if (size > input.limits.maxFileSizeBytes) {
    throw new PrepareFileTooLargeError();
  }

  const resizeApplied = actions.length > 0 || transformPasses > 1;
  const resizeReason = classifyResizeReason({
    edgeResize: edgeResize && resizeApplied,
    byteResize: byteResize || transformPasses > 1,
  });
  const formatConversionApplied = isFormatConversion({
    sourceMime,
    outputMime: mimeType,
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
    transformationProfile: buildTransformationProfileLabel({
      convertedFromHeic,
      resized: resizeApplied,
      heicPassthrough: isHeic && !needsHeicConvert,
    }),
    preparationProfileId: input.profile.profileId,
    preparationProfileVersion: input.profile.version,
    resizeApplied,
    reencodeApplied: true,
    formatConversionApplied,
    resizeReason,
    qualityApplied,
  };
}

function resolveJpegQuality(input: {
  readonly adaptiveQualityEnabled: boolean;
  readonly profileQuality: number;
  readonly willResize: boolean;
  readonly willConvertHeic: boolean;
}): number {
  if (input.adaptiveQualityEnabled) return input.profileQuality;
  if (input.willResize) return LEGACY_JPEG_QUALITY_RESIZE;
  if (input.willConvertHeic) return LEGACY_JPEG_QUALITY_CONVERT;
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
  if (!uri) return;
  await safeDelete(uri);
}

async function relocateTransform(sourceUri: string): Promise<string> {
  const dir = await ensureUploadTempDirectory();
  if (!dir) return sourceUri;
  const name = `xf-${Date.now()}-${Math.random().toString(36).slice(2, 10)}.jpg`;
  const dest = `${dir}${name}`;
  try {
    await FileSystem.copyAsync({ from: sourceUri, to: dest });
    if (sourceUri !== dest) await safeDelete(sourceUri);
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
