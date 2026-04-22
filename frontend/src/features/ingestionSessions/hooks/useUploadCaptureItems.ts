import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../../api/queryKeys';
import i18n from '../../../i18n';
import { uploadCaptureItem } from '../api/captureSessionsApi';

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

const CAPTURE_ITEM_UPLOAD_MAX_CONCURRENCY = 3;

async function runWithConcurrency<T>(
  workers: Array<() => Promise<T>>,
  maxConcurrent: number
): Promise<Array<PromiseSettledResult<T>>> {
  const out: Array<PromiseSettledResult<T>> = new Array(workers.length);
  let cursor = 0;
  async function workerLoop(): Promise<void> {
    while (cursor < workers.length) {
      const current = cursor;
      cursor += 1;
      try {
        const value = await workers[current]();
        out[current] = { status: 'fulfilled', value };
      } catch (reason) {
        out[current] = { status: 'rejected', reason };
      }
    }
  }
  const pool = Array.from({ length: Math.max(1, Math.min(maxConcurrent, workers.length)) }, () =>
    workerLoop()
  );
  await Promise.all(pool);
  return out;
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

      const workers = queue.map((entry) => async () => {
        entry.state = 'uploading';
        entry.progressPct = 0;
        entry.error = undefined;
        notify();
        try {
          await uploadCaptureItem(vars.inventoryId, vars.sessionId, entry.file, vars.aisleId, (pct) => {
            entry.progressPct = pct;
            notify();
          });
          entry.state = 'uploaded';
          entry.progressPct = 100;
          notify();
        } catch (error) {
          entry.state = 'failed';
          entry.error = error instanceof Error ? error.message : i18n.t('errors.request_failed');
          notify();
          throw error;
        }
      });

      await runWithConcurrency(workers, CAPTURE_ITEM_UPLOAD_MAX_CONCURRENCY);

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
