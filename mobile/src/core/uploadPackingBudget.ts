/**
 * Adaptive packing budget for multipart uploads.
 *
 * Server limits are the ceiling. On HTTP 413 we shrink the effective budget so the next
 * micro-batches fit. On success we relax back toward the server ceiling. Pure + deterministic.
 */

export interface PackingBudget {
  readonly maxFiles: number;
  readonly maxRequestBytes: number;
  readonly maxFileBytes: number;
}

export interface ServerPackingLimits {
  readonly maxFilesPerRequest: number;
  readonly maxRequestSizeBytes: number;
  readonly maxFileSizeBytes: number;
}

export function packingBudgetFromServer(limits: ServerPackingLimits): PackingBudget {
  const maxFiles = Math.max(1, limits.maxFilesPerRequest);
  const maxRequestBytes = Math.max(1, limits.maxRequestSizeBytes);
  const maxFileBytes = Math.max(1, Math.min(limits.maxFileSizeBytes, maxRequestBytes));
  return { maxFiles, maxRequestBytes, maxFileBytes };
}

/**
 * After a 413 on a concrete batch, shrink so a similar payload cannot be re-sent.
 * Never goes below 1 file / at least one prepared file's bytes (caller passes failedBatchBytes).
 */
export function shrinkPackingBudgetAfter413(input: {
  readonly current: PackingBudget;
  readonly server: ServerPackingLimits;
  readonly failedBatchFileCount: number;
  readonly failedBatchBytes: number;
}): PackingBudget {
  const server = packingBudgetFromServer(input.server);
  const failedFiles = Math.max(1, input.failedBatchFileCount);
  const failedBytes = Math.max(1, input.failedBatchBytes);

  const nextFiles = Math.max(1, Math.min(input.current.maxFiles, Math.floor(failedFiles / 2) || 1));
  // Leave headroom under the failed payload; floor at one file's fair share of the failure.
  const fairShare = Math.max(1, Math.floor(failedBytes / failedFiles));
  const nextRequest = Math.max(
    fairShare,
    Math.min(input.current.maxRequestBytes, Math.floor(failedBytes * 0.6)),
  );
  const nextFile = Math.max(1, Math.min(server.maxFileBytes, nextRequest, input.current.maxFileBytes));

  return {
    maxFiles: Math.min(server.maxFiles, nextFiles),
    maxRequestBytes: Math.min(server.maxRequestBytes, nextRequest),
    maxFileBytes: nextFile,
  };
}

/** After a successful upload, ease back toward server limits (not all the way in one step). */
export function relaxPackingBudgetAfterSuccess(input: {
  readonly current: PackingBudget;
  readonly server: ServerPackingLimits;
}): PackingBudget {
  const server = packingBudgetFromServer(input.server);
  const nextFiles = Math.min(server.maxFiles, Math.max(input.current.maxFiles + 1, input.current.maxFiles));
  const nextRequest = Math.min(
    server.maxRequestBytes,
    Math.max(input.current.maxRequestBytes, Math.floor(input.current.maxRequestBytes * 1.25)),
  );
  const nextFile = Math.min(server.maxFileBytes, Math.max(input.current.maxFileBytes, nextRequest));
  return {
    maxFiles: nextFiles,
    maxRequestBytes: nextRequest,
    maxFileBytes: Math.min(nextFile, nextRequest),
  };
}
