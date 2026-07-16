import * as FileSystem from 'expo-file-system';
import * as ImageManipulator from 'expo-image-manipulator';
import { isAllowedImageMime, normalizeMime } from '../../shared/constants/imageFormats';

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
 * Backend worker can normalize via pillow-heif, but multipart + storage path
 * compatibility is safer with JPEG for the mobile MVP.
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
  if (input.size <= 0) {
    throw new Error('Archivo vacío');
  }

  let uri = input.uri;
  let mimeType = mime === 'image/jpg' ? 'image/jpeg' : mime;
  let size = input.size;
  let transformUri: string | null = null;
  let convertedFromHeic = false;
  let displayName = input.displayName;

  const isHeic = mimeType === 'image/heic' || mimeType === 'image/heif';
  if (isHeic) {
    const result = await ImageManipulator.manipulateAsync(uri, [], {
      compress: 0.92,
      format: ImageManipulator.SaveFormat.JPEG,
    });
    uri = result.uri;
    transformUri = result.uri;
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
    uri = result.uri;
    transformUri = result.uri;
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
    originalSize: input.size,
    convertedFromHeic,
  };
}

export async function cleanupTransformUri(uri: string | null | undefined): Promise<void> {
  if (!uri) {
    return;
  }
  await safeDelete(uri);
}

async function safeDelete(uri: string): Promise<void> {
  try {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  } catch {
    // best-effort
  }
}
