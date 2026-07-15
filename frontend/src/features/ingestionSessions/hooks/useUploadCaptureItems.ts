/**
 * Capture staging upload via shared bulk uploader.
 * Selections larger than ``maxFilesPerRequest`` are auto-batched into sequential/concurrent POSTs.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../api/queryKeys';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import {
  executeBulkUpload,
  type BulkUploadFileResult,
  type BulkUploadProgressSnapshot,
} from '../../uploads';
import {
  CAPTURE_STAGING_MAX_FILES_PER_REQUEST,
  uploadCaptureSessionStagingBatch,
  stagingResponseToOutcomes,
} from '../api/captureSessionsApi';

export type UploadItemState = 'pending' | 'uploading' | 'uploaded' | 'failed' | 'cancelled';

export interface UploadQueueItem {
  key: string;
  file: File;
  state: UploadItemState;
  progressPct: number;
  error?: string;
  clientId?: string;
}

export interface UploadRunResult {
  queue: UploadQueueItem[];
  uploadedCount: number;
  failedCount: number;
  progress?: BulkUploadProgressSnapshot | null;
}

function toQueue(files: BulkUploadFileResult[]): UploadQueueItem[] {
  return files.map((f) => ({
    key: f.clientId,
    clientId: f.clientId,
    file: f.file,
    state:
      f.status === 'completed'
        ? 'uploaded'
        : f.status === 'failed'
          ? 'failed'
          : f.status === 'cancelled'
            ? 'cancelled'
            : f.status === 'uploading' || f.status === 'processing'
              ? 'uploading'
              : 'pending',
    progressPct: f.progress,
    error: f.errorMessage,
  }));
}

/** @deprecated Prefer executeBulkUpload outcomes; kept for unit tests of old mapping helpers. */
export function applyStagingChunkResult(
  queue: UploadQueueItem[],
  offset: number,
  chunkFiles: File[],
  result: { items: { import_status: string; last_error_code?: string | null; last_error_detail?: string | null }[]; errors: { file_index: number; code: string; detail: string }[] }
): void {
  const errByIdx = new Map(result.errors.map((e) => [e.file_index, e]));
  let itemCursor = 0;
  const { items } = result;
  for (let j = 0; j < chunkFiles.length; j++) {
    const entry = queue[offset + j];
    if (!entry) continue;
    const err = errByIdx.get(j);
    if (err) {
      entry.state = 'failed';
      entry.progressPct = 100;
      entry.error = `${err.code}: ${err.detail}`;
      continue;
    }
    const item = items[itemCursor++];
    if (!item) {
      entry.state = 'failed';
      entry.progressPct = 100;
      entry.error = 'Missing server item for this file';
      continue;
    }
    if (item.import_status !== 'imported') {
      entry.state = 'failed';
      entry.progressPct = 100;
      const code = item.last_error_code ?? item.import_status;
      const detail = item.last_error_detail?.trim() ? item.last_error_detail : '';
      entry.error = detail ? `${code}: ${detail}` : String(code);
      continue;
    }
    entry.state = 'uploaded';
    entry.progressPct = 100;
    entry.error = undefined;
  }
}

export function useUploadCaptureItems() {
  const queryClient = useQueryClient();
  const abortRef = { current: null as AbortController | null };
  const lastFilesRef = { current: null as BulkUploadFileResult[] | null };
  const lastBatchIdRef = { current: null as string | null };

  return useMutation({
    mutationFn: async (vars: {
      inventoryId: string;
      sessionId: string;
      aisleId?: string;
      files: File[];
      onlyFailed?: boolean;
      onQueueUpdate?: (queue: UploadQueueItem[]) => void;
      onProgress?: (snap: BulkUploadProgressSnapshot) => void;
      signal?: AbortSignal;
    }): Promise<UploadRunResult> => {
      const controller = vars.signal ? null : new AbortController();
      const signal = vars.signal ?? controller!.signal;
      abortRef.current = controller;

      const result = await executeBulkUpload({
        files: vars.files,
        signal,
        onProgress: (snap) => {
          vars.onProgress?.(snap);
          vars.onQueueUpdate?.(toQueue(snap.files));
        },
        existingFiles: vars.onlyFailed && lastFilesRef.current ? lastFilesRef.current : undefined,
        onlyClientIds:
          vars.onlyFailed && lastFilesRef.current
            ? new Set(lastFilesRef.current.filter((f) => f.status === 'failed').map((f) => f.clientId))
            : undefined,
        uploadBatchId: vars.onlyFailed && lastBatchIdRef.current ? lastBatchIdRef.current : undefined,
        uploadBatch: async ({ uploadBatchId, files: batchFiles, signal: batchSignal, onByteProgress }) => {
          const body = await uploadCaptureSessionStagingBatch({
            inventoryId: vars.inventoryId,
            sessionId: vars.sessionId,
            aisleId: vars.aisleId,
            files: batchFiles.map((f) => f.file),
            clientFileIds: batchFiles.map((f) => f.clientId),
            uploadBatchId,
            signal: batchSignal,
            onProgress: onByteProgress,
          });
          return stagingResponseToOutcomes(body, batchFiles.map((f) => f.clientId));
        },
      });

      lastFilesRef.current = result.files;
      lastBatchIdRef.current = result.uploadBatchId;
      const queue = toQueue(result.files);
      vars.onQueueUpdate?.(queue);
      return {
        queue,
        uploadedCount: result.completedCount,
        failedCount: result.failedCount,
      };
    },
    onSuccess: (_result, vars) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.captureSessions.detail(vars.inventoryId, vars.sessionId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.all });
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        resolveApiErrorMessage(error, 'errors.request_failed');
      }
    },
  });
}

export { CAPTURE_STAGING_MAX_FILES_PER_REQUEST };
