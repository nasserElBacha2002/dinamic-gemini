/**
 * Platform gate for bounded ZIP write (Android-only product + Node tests).
 */

import { ZipWriteError } from './zipWriteError';
import { isNodeRuntime } from './nodeRuntime';
import { missingNativeZipIoDetail, resolveNativeBinaryAppend } from './captureForegroundNative';

export type ZipWritePlatform = 'android' | 'node' | 'unsupported';

export function resolveZipWritePlatform(): ZipWritePlatform {
  if (isNodeRuntime()) {
    return 'node';
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const os = (require('react-native') as { Platform?: { OS?: string } }).Platform?.OS;
    if (os === 'android') {
      return 'android';
    }
  } catch {
    /* no RN */
  }
  return 'unsupported';
}

/**
 * Dinamic Captura is Android-only. Fail before starting ZIP I/O on unsupported platforms.
 * On Android, also require CaptureForegroundService.appendBase64File (Phase 5 native build).
 */
export function assertZipWritePlatformSupported(): void {
  const platform = resolveZipWritePlatform();
  if (platform === 'unsupported') {
    throw new ZipWriteError(
      'ZIP_WRITE_FAILED',
      'ZIP export requiere Android (cliente Android-only; no hay sink in-memory de respaldo)',
    );
  }
  if (platform === 'android' && !resolveNativeBinaryAppend()) {
    throw new ZipWriteError(
      'ZIP_WRITE_FAILED',
      `ZIP export requiere appendBase64File nativo (${missingNativeZipIoDetail()})`,
    );
  }
}
