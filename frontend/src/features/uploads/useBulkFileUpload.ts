import { useCallback, useRef, useState } from 'react';
import { executeBulkUpload } from './executeBulkUpload';
import type {
  BulkBatchUploader,
  BulkUploadFileResult,
  BulkUploadProgressSnapshot,
  BulkUploadRunResult,
} from './bulkUpload.types';

export function useBulkFileUpload() {
  const [snapshot, setSnapshot] = useState<BulkUploadProgressSnapshot | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastResultRef = useRef<BulkUploadRunResult | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const run = useCallback(
    async (args: {
      files: File[];
      uploadBatch: BulkBatchUploader;
      onlyFailed?: boolean;
    }): Promise<BulkUploadRunResult> => {
      if (isUploading) {
        throw new Error('Upload already in progress');
      }
      const controller = new AbortController();
      abortRef.current = controller;
      setIsUploading(true);
      try {
        const prev = lastResultRef.current;
        const result = await executeBulkUpload({
          files: args.files,
          uploadBatch: args.uploadBatch,
          signal: controller.signal,
          onProgress: setSnapshot,
          existingFiles: args.onlyFailed && prev ? prev.files : undefined,
          onlyClientIds:
            args.onlyFailed && prev
              ? new Set(prev.files.filter((f) => f.status === 'failed').map((f) => f.clientId))
              : undefined,
          uploadBatchId: args.onlyFailed && prev ? prev.uploadBatchId : undefined,
        });
        lastResultRef.current = result;
        return result;
      } finally {
        setIsUploading(false);
        abortRef.current = null;
      }
    },
    [isUploading]
  );

  const retryFailed = useCallback(
    async (uploadBatch: BulkBatchUploader) => {
      if (!lastResultRef.current) {
        throw new Error('No previous upload to retry');
      }
      return run({ files: [], uploadBatch, onlyFailed: true });
    },
    [run]
  );

  return {
    snapshot,
    isUploading,
    lastResult: lastResultRef.current as BulkUploadRunResult | null,
    lastFiles: (lastResultRef.current?.files ?? null) as BulkUploadFileResult[] | null,
    run,
    retryFailed,
    cancel,
  };
}
