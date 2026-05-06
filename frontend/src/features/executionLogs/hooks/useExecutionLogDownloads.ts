import { useCallback, useState } from 'react';
import {
  downloadAisleExecutionLogTxt,
  downloadExecutionLogTxt,
} from '../../../api/client';
import { ApiError } from '../../../api/types';

export interface UseExecutionLogDownloadsOptions {
  inventoryId: string;
  aisleId: string;
  downloadAisleExecutionLogTxtFn?: typeof downloadAisleExecutionLogTxt;
  downloadExecutionLogTxtFn?: typeof downloadExecutionLogTxt;
}

function normalizeApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error));
}

export function useExecutionLogDownloads({
  inventoryId,
  aisleId,
  downloadAisleExecutionLogTxtFn,
  downloadExecutionLogTxtFn,
}: UseExecutionLogDownloadsOptions) {
  const [isDownloadingMerged, setIsDownloadingMerged] = useState(false);
  const [isDownloadingJobLog, setIsDownloadingJobLog] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const downloadMergedExecutionLog = useCallback(async (): Promise<void> => {
    setIsDownloadingMerged(true);
    setError(null);
    try {
      const doDownload = downloadAisleExecutionLogTxtFn ?? downloadAisleExecutionLogTxt;
      await doDownload(inventoryId, aisleId);
    } catch (e) {
      const err = normalizeApiError(e);
      setError(err);
      throw err;
    } finally {
      setIsDownloadingMerged(false);
    }
  }, [aisleId, downloadAisleExecutionLogTxtFn, inventoryId]);

  const downloadJobExecutionLog = useCallback(
    async (jobId: string): Promise<void> => {
      setIsDownloadingJobLog(true);
      setError(null);
      try {
        const doDownload = downloadExecutionLogTxtFn ?? downloadExecutionLogTxt;
        await doDownload(inventoryId, aisleId, jobId);
      } catch (e) {
        const err = normalizeApiError(e);
        setError(err);
        throw err;
      } finally {
        setIsDownloadingJobLog(false);
      }
    },
    [aisleId, downloadExecutionLogTxtFn, inventoryId]
  );

  return {
    downloadMergedExecutionLog,
    downloadJobExecutionLog,
    isDownloadingMerged,
    isDownloadingJobLog,
    error,
    clearError,
  };
}
