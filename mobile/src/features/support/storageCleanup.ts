import * as FileSystem from 'expo-file-system';
import type { Logger } from '../../core/logging';
import {
  emptyCleanupResult,
  cleanupOutcomeLabel,
  type CleanupResult,
} from '../exportPrep/cleanupTypes';
import { assertSafeSandboxDeleteTarget } from '../exportPrep/safeSandboxPath';

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
 * Returns structured result — partial failures are not reported as full success.
 */
export async function cleanupTransformTemps(
  logger?: Logger,
  maxAgeMs: number = TEMP_MAX_AGE_MS,
  limits?: { readonly maxFiles?: number },
): Promise<CleanupResult> {
  const started = Date.now();
  const dir = uploadTempDirectory();
  if (!dir) {
    return emptyCleanupResult(started);
  }
  const maxFiles = limits?.maxFiles ?? 200;
  let scanned = 0;
  let deleted = 0;
  let bytesRecovered = 0;
  const errors: import('../exportPrep/cleanupTypes').CleanupError[] = [];
  try {
    const info = await FileSystem.getInfoAsync(dir);
    if (!info.exists) {
      return emptyCleanupResult(started);
    }
    const entries = await FileSystem.readDirectoryAsync(dir);
    const now = Date.now();
    const roots = {
      documentDirectory: FileSystem.documentDirectory,
      cacheDirectory: FileSystem.cacheDirectory,
    };
    for (const name of entries) {
      if (scanned >= maxFiles) break;
      scanned += 1;
      const path = `${dir}${name}`;
      try {
        assertSafeSandboxDeleteTarget(path, roots, {
          allowedPrefixes: ['dinamic-upload/'],
        });
        const meta = await FileSystem.getInfoAsync(path, { size: true });
        const mtime =
          meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number'
            ? meta.modificationTime * 1000
            : 0;
        if (mtime && now - mtime < maxAgeMs) {
          continue;
        }
        const size = meta.exists && typeof meta.size === 'number' ? meta.size : 0;
        await FileSystem.deleteAsync(path, { idempotent: true });
        deleted += 1;
        bytesRecovered += size;
      } catch (error) {
        errors.push({
          code: 'TRANSFORM_TEMP_DELETE_FAILED',
          artifactType: 'transform_temp',
          operation: 'delete',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  } catch (error) {
    errors.push({
      code: 'TRANSFORM_TEMP_SCAN_FAILED',
      artifactType: 'transform_temp',
      operation: 'scan',
      recoverable: true,
      message: error instanceof Error ? error.message : String(error),
    });
  }
  const result: CleanupResult = {
    scanned,
    deleted,
    quarantined: 0,
    recovered: 0,
    invalidated: 0,
    skippedActive: 0,
    failed: errors.length,
    errors,
    durationMs: Date.now() - started,
    bytesRecovered,
  };
  const label = cleanupOutcomeLabel(result);
  logger?.info(label === 'completed' ? 'storage.cleanup_completed' : 'storage.cleanup_partial', {
    removed: deleted,
    scanned,
    failed: errors.length,
    dir: UPLOAD_TEMP_DIR_NAME,
    durationMs: result.durationMs,
  });
  return result;
}
