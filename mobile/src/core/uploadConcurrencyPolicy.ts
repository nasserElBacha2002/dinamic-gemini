/**
 * Phase 1 — bounded upload concurrency policy (pure).
 */

import type { NormalizedNetworkType } from '../observability/types';

export interface UploadConcurrencyContext {
  readonly networkType: NormalizedNetworkType;
  /** Advisory from /upload-limits (server). */
  readonly serverConcurrency: number;
  readonly adaptiveConcurrencyEnabled: boolean;
  /** Hard ceiling even when adaptive is on. */
  readonly absoluteMax?: number;
}

export interface UploadConcurrencyPolicy {
  resolve(input: UploadConcurrencyContext): number;
}

/** Conservative defaults — not unlimited. */
export const UPLOAD_CONCURRENCY_WIFI_ETHERNET = 3;
export const UPLOAD_CONCURRENCY_CELLULAR = 2;
export const UPLOAD_CONCURRENCY_UNKNOWN = 2;
export const UPLOAD_CONCURRENCY_LEGACY_CAP = 2;
export const UPLOAD_CONCURRENCY_ABSOLUTE_MAX = 4;

export class DefaultUploadConcurrencyPolicy implements UploadConcurrencyPolicy {
  resolve(input: UploadConcurrencyContext): number {
    const server = Math.max(1, Math.floor(input.serverConcurrency || 1));
    const absoluteMax = Math.max(
      1,
      Math.min(UPLOAD_CONCURRENCY_ABSOLUTE_MAX, input.absoluteMax ?? UPLOAD_CONCURRENCY_ABSOLUTE_MAX),
    );

    if (input.networkType === 'offline') {
      return 0;
    }

    if (!input.adaptiveConcurrencyEnabled) {
      return Math.min(UPLOAD_CONCURRENCY_LEGACY_CAP, server, absoluteMax);
    }

    let desired: number;
    switch (input.networkType) {
      case 'wifi':
      case 'ethernet':
        desired = UPLOAD_CONCURRENCY_WIFI_ETHERNET;
        break;
      case 'cellular':
        desired = UPLOAD_CONCURRENCY_CELLULAR;
        break;
      default:
        desired = UPLOAD_CONCURRENCY_UNKNOWN;
        break;
    }

    return Math.max(1, Math.min(desired, server, absoluteMax));
  }
}

export const defaultUploadConcurrencyPolicy = new DefaultUploadConcurrencyPolicy();
