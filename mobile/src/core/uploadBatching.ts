export interface BatchCandidate {
  readonly photoId: string;
  readonly clientFileId: string;
  readonly sizeBytes: number;
  readonly dateAdded: number;
  readonly assetId: string;
}

export interface MicroBatchLimits {
  readonly maxFilesPerRequest: number;
  readonly maxFileSizeBytes: number;
  readonly maxRequestSizeBytes: number;
  /**
   * When true (prepare-first pipeline), only candidates with sizeBytes > 0 are packed.
   * Unknown sizes must be prepared before batching so request budgets are real.
   */
  readonly requirePositiveSize?: boolean;
}

export interface MicroBatch {
  readonly photoIds: readonly string[];
  readonly clientFileIds: readonly string[];
  readonly totalBytes: number;
}

/**
 * Build one micro-batch from queued candidates. Pure.
 *
 * Prepare-first mode (`requirePositiveSize: true`): packs only known positive sizes and never
 * exceeds maxRequestSizeBytes / maxFilesPerRequest. A single file larger than maxFileSizeBytes
 * is skipped (caller should re-prepare or mark permanent_error).
 *
 * Legacy mode (default): unknown/oversized reported sizes may be included so prepare can run
 * inside an older upload path; prefer prepare-first for production captures (20+ photos).
 */
export function buildMicroBatch(
  candidates: readonly BatchCandidate[],
  limits: MicroBatchLimits,
): MicroBatch | null {
  const requirePositive = limits.requirePositiveSize === true;
  const sorted = [...candidates].sort((a, b) => {
    if (a.dateAdded !== b.dateAdded) {
      return a.dateAdded - b.dateAdded;
    }
    return a.assetId.localeCompare(b.assetId);
  });
  const photoIds: string[] = [];
  const clientFileIds: string[] = [];
  let totalBytes = 0;

  for (const item of sorted) {
    if (photoIds.length >= limits.maxFilesPerRequest) {
      break;
    }

    if (requirePositive) {
      if (!(item.sizeBytes > 0)) {
        continue;
      }
      if (item.sizeBytes > limits.maxFileSizeBytes) {
        continue;
      }
      if (totalBytes + item.sizeBytes > limits.maxRequestSizeBytes) {
        if (photoIds.length === 0) {
          // Single prepared file still exceeds request budget — cannot pack; leave for recalibration.
          continue;
        }
        break;
      }
      photoIds.push(item.photoId);
      clientFileIds.push(item.clientFileId);
      totalBytes += item.sizeBytes;
      continue;
    }

    // Legacy: unknown size contributes 0; oversized reported size is capped for packing only.
    const accounted =
      item.sizeBytes > 0 ? Math.min(item.sizeBytes, limits.maxFileSizeBytes) : 0;
    if (accounted > 0 && totalBytes + accounted > limits.maxRequestSizeBytes) {
      if (photoIds.length === 0) {
        photoIds.push(item.photoId);
        clientFileIds.push(item.clientFileId);
        totalBytes += accounted;
        break;
      }
      break;
    }
    photoIds.push(item.photoId);
    clientFileIds.push(item.clientFileId);
    totalBytes += accounted;
  }

  if (photoIds.length === 0) {
    return null;
  }
  return { photoIds, clientFileIds, totalBytes };
}

export function buildAllMicroBatches(
  candidates: readonly BatchCandidate[],
  limits: MicroBatchLimits,
): MicroBatch[] {
  const remaining = [...candidates];
  const batches: MicroBatch[] = [];
  while (remaining.length > 0) {
    const batch = buildMicroBatch(remaining, limits);
    if (!batch) {
      break;
    }
    const taken = new Set(batch.photoIds);
    for (let i = remaining.length - 1; i >= 0; i -= 1) {
      const item = remaining[i];
      if (item && taken.has(item.photoId)) {
        remaining.splice(i, 1);
      }
    }
    batches.push(batch);
  }
  return batches;
}
