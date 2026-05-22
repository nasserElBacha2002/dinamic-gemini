/**
 * Capture staging upload from the browser.
 *
 * **Transport policy:** uploads run as **sequential HTTP POSTs**, each carrying up to
 * At most ``CAPTURE_STAGING_MAX_FILES_PER_REQUEST`` (5) files per HTTP POST. Selections
 * larger than that are rejected in the UI/API client before upload starts.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../api/queryKeys';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { isTooManyFilesForUpload, tooManyFilesMessage } from '../../../utils/uploadFileLimits';
import { uploadCaptureSessionStagingFiles } from '../api/captureSessionsApi';
import type { UploadCaptureSessionItemsResponse } from '../../../types/captureSession';

export type UploadItemState = 'pending' | 'uploading' | 'uploaded' | 'failed';

export interface UploadQueueItem {
  key: string;
  file: File;
  state: UploadItemState;
  progressPct: number;
  error?: string;
}

export interface UploadRunResult {
  queue: UploadQueueItem[];
  uploadedCount: number;
  failedCount: number;
}

/** Maps one staging POST (≤ max files) onto the corresponding slice of the UI queue. Exported for tests. */
export function applyStagingChunkResult(
  queue: UploadQueueItem[],
  offset: number,
  chunkFiles: File[],
  result: UploadCaptureSessionItemsResponse
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
  return useMutation({
    mutationFn: async (vars: {
      inventoryId: string;
      sessionId: string;
      aisleId?: string;
      files: File[];
      onQueueUpdate?: (queue: UploadQueueItem[]) => void;
    }): Promise<UploadRunResult> => {
      const queue: UploadQueueItem[] = vars.files.map((file) => ({
        key: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
        file,
        state: 'pending',
        progressPct: 0,
      }));

      const notify = () => vars.onQueueUpdate?.(queue.map((q) => ({ ...q })));

      if (isTooManyFilesForUpload(queue.length)) {
        throw new ApiError(tooManyFilesMessage('import'));
      }

      for (const entry of queue) {
        entry.state = 'uploading';
        entry.progressPct = 0;
        entry.error = undefined;
      }
      notify();
      const chunkFiles = queue.map((e) => e.file);
      try {
        const result = await uploadCaptureSessionStagingFiles(
          vars.inventoryId,
          vars.sessionId,
          chunkFiles,
          vars.aisleId,
          (pct) => {
            for (const entry of queue) {
              entry.progressPct = pct;
            }
            notify();
          }
        );
        applyStagingChunkResult(queue, 0, chunkFiles, result);
        notify();
      } catch (error) {
        const msg = resolveApiErrorMessage(error, 'errors.request_failed');
        for (const entry of queue) {
          entry.state = 'failed';
          entry.progressPct = 100;
          entry.error = msg;
        }
        notify();
      }

      const uploadedCount = queue.filter((q) => q.state === 'uploaded').length;
      const failedCount = queue.filter((q) => q.state === 'failed').length;
      return { queue, uploadedCount, failedCount };
    },
    onSuccess: (_result, vars) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.captureSessions.detail(vars.inventoryId, vars.sessionId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.captureSessions.all });
    },
  });
}
