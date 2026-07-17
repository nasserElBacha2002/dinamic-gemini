import * as FileSystem from 'expo-file-system';
import type { Logger } from '../../core/logging';

export const UPLOAD_TEMP_DIR_NAME = 'dinamic-upload';

/** Configurable max age for orphan temps (default 48h). */
export const TEMP_MAX_AGE_MS = 48 * 60 * 60 * 1000;

export interface StorageStatus {
  readonly freeBytes: number | null;
  readonly totalBytes: number | null;
  readonly lowSpace: boolean;
}

/** Conservative threshold: warn below 500 MB free. */
export const LOW_SPACE_BYTES = 500 * 1024 * 1024;

export function uploadTempDirectory(): string | null {
  const cache = FileSystem.cacheDirectory;
  if (!cache) {
    return null;
  }
  return `${cache}${UPLOAD_TEMP_DIR_NAME}/`;
}

export async function ensureUploadTempDirectory(): Promise<string | null> {
  const dir = uploadTempDirectory();
  if (!dir) {
    return null;
  }
  const info = await FileSystem.getInfoAsync(dir);
  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
  }
  return dir;
}

export async function getStorageStatus(): Promise<StorageStatus> {
  try {
    const free = await FileSystem.getFreeDiskStorageAsync();
    const total = await FileSystem.getTotalDiskCapacityAsync();
    return {
      freeBytes: free,
      totalBytes: total,
      lowSpace: free < LOW_SPACE_BYTES,
    };
  } catch {
    return { freeBytes: null, totalBytes: null, lowSpace: false };
  }
}

/**
 * Cleanup only files under cacheDirectory/dinamic-upload/.
 * Never deletes MediaStore originals. Does not scan arbitrary .jpg files.
 */
export async function cleanupTransformTemps(
  logger?: Logger,
  maxAgeMs: number = TEMP_MAX_AGE_MS,
): Promise<number> {
  const dir = uploadTempDirectory();
  if (!dir) {
    return 0;
  }
  let removed = 0;
  try {
    const info = await FileSystem.getInfoAsync(dir);
    if (!info.exists) {
      return 0;
    }
    const entries = await FileSystem.readDirectoryAsync(dir);
    const now = Date.now();
    for (const name of entries) {
      const path = `${dir}${name}`;
      try {
        const meta = await FileSystem.getInfoAsync(path);
        const mtime =
          meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number'
            ? meta.modificationTime * 1000
            : 0;
        if (mtime && now - mtime < maxAgeMs) {
          continue;
        }
        await FileSystem.deleteAsync(path, { idempotent: true });
        removed += 1;
      } catch {
        // ignore
      }
    }
  } catch {
    // ignore
  }
  logger?.info('storage_cleanup', { removed, dir: UPLOAD_TEMP_DIR_NAME });
  return removed;
}
