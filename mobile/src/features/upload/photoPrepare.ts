import * as FileSystem from 'expo-file-system';
import * as ImageManipulator from 'expo-image-manipulator';
import { isAllowedImageMime, normalizeMime } from '../../shared/constants/imageFormats';
import { ensureUploadTempDirectory } from '../support/storageCleanup';

export interface PreparedUploadFile {
  readonly uri: string;
  readonly mimeType: string;
  readonly size: number;
  readonly displayName: string;
  readonly transformUri: string | null;
  readonly originalSize: number;
  readonly convertedFromHeic: boolean;
}

export interface PrepareLimits {
  readonly maxFileSizeBytes: number;
}

/**
 * HEIC/HEIF: convert to JPEG on device before upload.
 * Transform outputs live under cacheDirectory/dinamic-upload/ only.
 */
export async function preparePhotoForUpload(input: {
  readonly uri: string;
  readonly mimeType: string;
  readonly displayName: string;
  readonly size: number;
  readonly width: number;
  readonly height: number;
  readonly limits: PrepareLimits;
}): Promise<PreparedUploadFile> {
  const mime = normalizeMime(input.mimeType);
  if (!isAllowedImageMime(mime)) {
    throw new Error(`MIME no permitido: ${mime || 'unknown'}`);
  }

  let size = input.size;
  if (!(size > 0)) {
    // Gallery hydration often reports 0 for content:// URIs; re-stat before rejecting.
    try {
      const info = await FileSystem.getInfoAsync(input.uri, { size: true });
      if (info.exists && typeof info.size === 'number' && info.size > 0) {
        size = info.size;
      }
    } catch {
      // fall through to empty check
    }
  }
  if (!(size > 0)) {
    throw new Error('Archivo vacío');
  }

  let uri = input.uri;
  let mimeType = mime === 'image/jpg' ? 'image/jpeg' : mime;
  let transformUri: string | null = null;
  let convertedFromHeic = false;
  let displayName = input.displayName;

  const isHeic = mimeType === 'image/heic' || mimeType === 'image/heif';
  if (isHeic) {
    const result = await ImageManipulator.manipulateAsync(uri, [], {
      compress: 0.92,
      format: ImageManipulator.SaveFormat.JPEG,
    });
    uri = await relocateTransform(result.uri);
    transformUri = uri;
    mimeType = 'image/jpeg';
    convertedFromHeic = true;
    displayName = displayName.replace(/\.(heic|heif)$/i, '.jpg');
    const info = await FileSystem.getInfoAsync(uri);
    size = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : size;
  }

  if (size > input.limits.maxFileSizeBytes) {
    const scale = Math.sqrt(input.limits.maxFileSizeBytes / size) * 0.95;
    const width = Math.max(640, Math.floor(input.width * Math.min(1, scale)));
    const result = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width } }],
      { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG },
    );
    if (transformUri && transformUri !== input.uri) {
      await safeDelete(transformUri);
    }
    uri = await relocateTransform(result.uri);
    transformUri = uri;
    mimeType = 'image/jpeg';
    displayName = displayName.replace(/\.[^.]+$/, '.jpg');
    const info = await FileSystem.getInfoAsync(uri);
    size = info.exists && 'size' in info && typeof info.size === 'number' ? info.size : size;
  }

  if (size > input.limits.maxFileSizeBytes) {
    throw new Error('Archivo demasiado grande tras transformar');
  }

  return {
    uri,
    mimeType,
    size,
    displayName,
    transformUri,
    originalSize: size,
    convertedFromHeic,
  };
}

export async function cleanupTransformUri(uri: string | null | undefined): Promise<void> {
  if (!uri) {
    return;
  }
  await safeDelete(uri);
}

/** Move manipulator output into the app-owned temp directory. */
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
