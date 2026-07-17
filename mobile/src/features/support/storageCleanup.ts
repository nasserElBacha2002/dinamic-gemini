import * as FileSystem from 'expo-file-system';
import type { Logger } from '../../core/logging';

const TEMP_PREFIX = 'dinamic-upload-';

export interface StorageStatus {
  readonly freeBytes: number | null;
  readonly totalBytes: number | null;
  readonly lowSpace: boolean;
}

/** Conservative threshold: warn below 500 MB free. */
export const LOW_SPACE_BYTES = 500 * 1024 * 1024;

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
 * Best-effort cleanup of transform temps under cache directory.
 * Never deletes original gallery photos.
 */
export async function cleanupTransformTemps(logger?: Logger): Promise<number> {
  const cache = FileSystem.cacheDirectory;
  if (!cache) {
    return 0;
  }
  let removed = 0;
  try {
    const entries = await FileSystem.readDirectoryAsync(cache);
    for (const name of entries) {
      if (!name.includes(TEMP_PREFIX) && !name.endsWith('.jpg') && !name.includes('ImageManipulator')) {
        continue;
      }
      // Only delete ImageManipulator / known temp patterns — keep conservative.
      if (name.includes('ImageManipulator') || name.startsWith(TEMP_PREFIX)) {
        try {
          await FileSystem.deleteAsync(`${cache}${name}`, { idempotent: true });
          removed += 1;
        } catch {
          // ignore
        }
      }
    }
  } catch {
    // ignore
  }
  logger?.info('storage_cleanup', { removed });
  return removed;
}
