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
}

export interface MicroBatch {
  readonly photoIds: readonly string[];
  readonly clientFileIds: readonly string[];
  readonly totalBytes: number;
}

/** Build one micro-batch from queued candidates. Pure. */
export function buildMicroBatch(
  candidates: readonly BatchCandidate[],
  limits: MicroBatchLimits,
): MicroBatch | null {
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
    if (item.sizeBytes <= 0 || item.sizeBytes > limits.maxFileSizeBytes) {
      continue;
    }
    if (photoIds.length >= limits.maxFilesPerRequest) {
      break;
    }
    if (totalBytes + item.sizeBytes > limits.maxRequestSizeBytes) {
      if (photoIds.length === 0) {
        continue;
      }
      break;
    }
    photoIds.push(item.photoId);
    clientFileIds.push(item.clientFileId);
    totalBytes += item.sizeBytes;
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
