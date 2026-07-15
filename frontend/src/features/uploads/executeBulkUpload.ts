import { UPLOAD_LIMITS } from './bulkUpload.config';
import { createUploadBatches, partitionUploadFiles } from './createUploadBatches';
import type {
  BulkBatchUploader,
  BulkUploadFileResult,
  BulkUploadProgressSnapshot,
  BulkUploadRunResult,
  UploadErrorCode,
} from './bulkUpload.types';
import {
  isAbortError,
  isRetryableUploadErrorCode,
  isTransientHttpStatus,
  mapHttpStatusToUploadErrorCode,
  retryDelayMs,
  sleep,
} from './uploadRetryPolicy';
import { newUploadUuid } from './uploadIds';
import { ApiError } from '../../api/types';

function newBatchId(): string {
  return newUploadUuid();
}

function snapshotFrom(
  uploadBatchId: string,
  files: BulkUploadFileResult[],
  batchesCompleted: number,
  batchesTotal: number,
  phase: BulkUploadProgressSnapshot['phase'],
  uploadedBytes: number
): BulkUploadProgressSnapshot {
  const completedCount = files.filter((f) => f.status === 'completed').length;
  const failedCount = files.filter((f) => f.status === 'failed').length;
  const cancelledCount = files.filter((f) => f.status === 'cancelled').length;
  const totalBytes = files.reduce((s, f) => s + f.file.size, 0);
  const clampedBytes = Math.max(0, Math.min(totalBytes, uploadedBytes));
  const progressPct =
    totalBytes <= 0 ? 100 : Math.min(100, Math.round((clampedBytes / totalBytes) * 100));
  return {
    uploadBatchId,
    phase,
    files: files.map((f) => ({ ...f })),
    completedCount,
    failedCount,
    cancelledCount,
    totalCount: files.length,
    uploadedBytes: clampedBytes,
    totalBytes,
    progressPct,
    batchesCompleted,
    batchesTotal,
  };
}

function mapUnknownError(err: unknown): { code: UploadErrorCode; message: string } {
  if (err instanceof ApiError) {
    const status = err.status ?? 0;
    const codeFromStatus = mapHttpStatusToUploadErrorCode(status);
    const raw = typeof err.data?.code === 'string' ? err.data.code : codeFromStatus;
    const code = (raw as UploadErrorCode) || codeFromStatus;
    return { code, message: err.message };
  }
  if (isAbortError(err)) {
    return { code: 'UNKNOWN', message: 'cancelled' };
  }
  return { code: 'NETWORK_ERROR', message: err instanceof Error ? err.message : String(err) };
}

export interface ExecuteBulkUploadOptions {
  files: File[];
  uploadBatch: BulkBatchUploader;
  signal?: AbortSignal;
  onProgress?: (snap: BulkUploadProgressSnapshot) => void;
  onlyClientIds?: Set<string>;
  existingFiles?: BulkUploadFileResult[];
  uploadBatchId?: string;
  maxFilesPerBatch?: number;
  maxBytesPerBatch?: number;
  maxFileSizeBytes?: number;
  concurrency?: number;
  retryAttempts?: number;
  retryBaseDelayMs?: number;
}

export async function executeBulkUpload(options: ExecuteBulkUploadOptions): Promise<BulkUploadRunResult> {
  const maxFilesPerBatch = options.maxFilesPerBatch ?? UPLOAD_LIMITS.maxFilesPerRequest;
  const maxBytesPerBatch = options.maxBytesPerBatch ?? UPLOAD_LIMITS.maxBytesPerRequest;
  const maxFileSizeBytes = options.maxFileSizeBytes ?? UPLOAD_LIMITS.maxFileSizeBytes;
  const concurrency = Math.max(1, options.concurrency ?? UPLOAD_LIMITS.uploadConcurrency);
  const retryAttempts = Math.max(1, options.retryAttempts ?? UPLOAD_LIMITS.retryAttempts);
  const retryBaseDelayMs = Math.max(0, options.retryBaseDelayMs ?? UPLOAD_LIMITS.retryBaseDelayMs);

  const uploadBatchId = options.uploadBatchId ?? newBatchId();
  let allFiles: BulkUploadFileResult[];

  if (options.existingFiles && options.onlyClientIds) {
    allFiles = options.existingFiles.map((f) => ({ ...f }));
    for (const f of allFiles) {
      if (options.onlyClientIds.has(f.clientId) && f.status === 'failed') {
        f.status = 'pending';
        f.progress = 0;
        f.errorCode = undefined;
        f.errorMessage = undefined;
        f.attempts = 0;
      }
    }
  } else {
    const { valid, oversized } = partitionUploadFiles(options.files, {
      maxFilesPerBatch,
      maxBytesPerBatch,
      maxFileSizeBytes,
    });
    allFiles = [...valid, ...oversized];
  }

  const pending = allFiles.filter((f) => f.status === 'pending');
  const batches = createUploadBatches(pending, { maxFilesPerBatch, maxBytesPerBatch });
  const batchesTotal = batches.length;
  let batchesCompleted = 0;

  /** Bytes fully committed from completed batches (and failed/cancelled file sizes that are "done"). */
  let completedBytes = allFiles
    .filter((f) => f.status === 'completed' || f.status === 'failed')
    .reduce((s, f) => s + f.file.size, 0);
  const loadedBytesByBatch = new Map<number, number>();
  let lastEmittedBytes = completedBytes;

  const globalUploadedBytes = () => {
    let active = 0;
    for (const v of loadedBytesByBatch.values()) active += v;
    return completedBytes + active;
  };

  const notify = (phase: BulkUploadProgressSnapshot['phase']) => {
    const bytes = globalUploadedBytes();
    // Monotonic unless starting a fresh upload (phase preparing not used mid-run).
    const monotonic = Math.max(lastEmittedBytes, bytes);
    lastEmittedBytes = Math.min(
      allFiles.reduce((s, f) => s + f.file.size, 0),
      monotonic
    );
    options.onProgress?.(
      snapshotFrom(uploadBatchId, allFiles, batchesCompleted, batchesTotal, phase, lastEmittedBytes)
    );
  };

  notify(
    pending.length
      ? 'uploading'
      : allFiles.some((f) => f.status === 'failed')
        ? 'completed_with_errors'
        : 'completed'
  );

  if (options.signal?.aborted) {
    markCancelled(allFiles);
    notify('cancelled');
    return finalize(uploadBatchId, allFiles);
  }

  let nextIndex = 0;
  const runWorker = async (): Promise<void> => {
    while (true) {
      if (options.signal?.aborted) return;
      const idx = nextIndex++;
      if (idx >= batches.length) return;
      const batch = batches[idx];
      loadedBytesByBatch.set(idx, 0);
      try {
        await uploadOneBatch({
          uploadBatchId,
          batchFiles: batch.files,
          uploader: options.uploadBatch,
          signal: options.signal,
          retryAttempts,
          retryBaseDelayMs,
          onProgress: (loaded, total) => {
            const frac = total > 0 ? Math.min(1, loaded / total) : 0;
            loadedBytesByBatch.set(idx, Math.round(batch.totalBytes * frac));
            for (const f of batch.files) {
              if (f.status === 'uploading') {
                f.progress = Math.min(99, Math.round(frac * 100));
              }
            }
            notify('uploading');
          },
        });
      } finally {
        const stillActive = batch.files.some(
          (f) => f.status === 'uploading' || f.status === 'processing' || f.status === 'pending'
        );
        if (!stillActive) {
          // Move batch contribution into completedBytes once terminal.
          const doneBytes = batch.files
            .filter((f) => f.status === 'completed' || f.status === 'failed')
            .reduce((s, f) => s + f.file.size, 0);
          loadedBytesByBatch.delete(idx);
          // completedBytes already includes prior completed/failed; add this batch's newly terminal sizes
          // by recounting from files to avoid double-count:
          completedBytes = allFiles
            .filter((f) => f.status === 'completed' || f.status === 'failed')
            .reduce((s, f) => s + f.file.size, 0);
          void doneBytes;
        }
        batchesCompleted += 1;
        notify(options.signal?.aborted ? 'cancelled' : 'uploading');
      }
    }
  };

  const workers = Array.from({ length: Math.min(concurrency, Math.max(1, batches.length)) }, () =>
    runWorker()
  );
  await Promise.all(workers);

  if (options.signal?.aborted) {
    markCancelled(allFiles);
    notify('cancelled');
  } else {
    const failed = allFiles.some((f) => f.status === 'failed');
    lastEmittedBytes = allFiles.reduce((s, f) => s + f.file.size, 0);
    notify(failed ? 'completed_with_errors' : 'completed');
  }

  return finalize(uploadBatchId, allFiles);
}

function markCancelled(files: BulkUploadFileResult[]): void {
  for (const f of files) {
    if (f.status === 'pending' || f.status === 'uploading' || f.status === 'processing') {
      f.status = 'cancelled';
    }
  }
}

async function uploadOneBatch(args: {
  uploadBatchId: string;
  batchFiles: BulkUploadFileResult[];
  uploader: BulkBatchUploader;
  signal?: AbortSignal;
  retryAttempts: number;
  retryBaseDelayMs: number;
  onProgress: (loaded: number, total: number) => void;
}): Promise<void> {
  for (const f of args.batchFiles) {
    f.status = 'uploading';
    f.progress = 0;
  }

  let attempt = 0;
  while (attempt < args.retryAttempts) {
    if (args.signal?.aborted) return;
    attempt += 1;
    for (const f of args.batchFiles) {
      f.attempts = attempt;
    }
    try {
      const result = await args.uploader({
        uploadBatchId: args.uploadBatchId,
        files: args.batchFiles,
        signal: args.signal ?? new AbortController().signal,
        onByteProgress: args.onProgress,
      });
      const byId = new Map(result.outcomes.map((o) => [o.clientFileId, o]));
      for (const f of args.batchFiles) {
        const o = byId.get(f.clientId);
        if (!o) {
          f.status = 'failed';
          f.progress = 100;
          f.errorCode = 'UNKNOWN';
          f.errorMessage = 'Missing server outcome for file';
          continue;
        }
        if (o.status === 'completed') {
          f.status = 'completed';
          f.progress = 100;
          f.serverId = o.serverId;
          f.errorCode = undefined;
          f.errorMessage = undefined;
        } else {
          f.status = 'failed';
          f.progress = 100;
          f.errorCode = (o.code as UploadErrorCode) || 'UNKNOWN';
          f.errorMessage = o.message || o.code || 'failed';
        }
      }
      return;
    } catch (err) {
      if (isAbortError(err) || args.signal?.aborted) {
        return;
      }
      const mapped = mapUnknownError(err);
      const status = err instanceof ApiError ? err.status ?? 0 : 0;
      const retryable =
        isTransientHttpStatus(status) || isRetryableUploadErrorCode(mapped.code);
      if (!retryable || attempt >= args.retryAttempts) {
        for (const f of args.batchFiles) {
          if (f.status === 'completed') continue;
          f.status = 'failed';
          f.progress = 100;
          f.errorCode = mapped.code;
          f.errorMessage = mapped.message;
        }
        return;
      }
      try {
        await sleep(retryDelayMs(attempt, args.retryBaseDelayMs), args.signal);
      } catch (sleepErr) {
        if (isAbortError(sleepErr) || args.signal?.aborted) {
          return;
        }
        throw sleepErr;
      }
    }
  }
}

function finalize(uploadBatchId: string, files: BulkUploadFileResult[]): BulkUploadRunResult {
  return {
    uploadBatchId,
    files,
    completedCount: files.filter((f) => f.status === 'completed').length,
    failedCount: files.filter((f) => f.status === 'failed').length,
    cancelledCount: files.filter((f) => f.status === 'cancelled').length,
    uploadedBytes: files.filter((f) => f.status === 'completed').reduce((s, f) => s + f.file.size, 0),
    totalBytes: files.reduce((s, f) => s + f.file.size, 0),
  };
}
