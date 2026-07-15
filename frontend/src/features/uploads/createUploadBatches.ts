import type { BulkUploadBatchPlan, BulkUploadFileResult, CreateUploadBatchesOptions } from './bulkUpload.types';
import { newUploadUuid } from './uploadIds';

function newClientId(): string {
  return newUploadUuid();
}

/**
 * Pure batching: respects both max files and max accumulated bytes per batch.
 * Oversized individual files are placed alone in a 0-file sense — callers should
 * mark them failed before calling this, or pass only valid files.
 *
 * Files larger than ``maxFileSizeBytes`` are returned in ``oversized`` and omitted
 * from batches.
 */
export function partitionUploadFiles(
  files: File[],
  options: CreateUploadBatchesOptions
): { valid: BulkUploadFileResult[]; oversized: BulkUploadFileResult[] } {
  const valid: BulkUploadFileResult[] = [];
  const oversized: BulkUploadFileResult[] = [];
  for (const file of files) {
    const row: BulkUploadFileResult = {
      clientId: newClientId(),
      file,
      status: 'pending',
      progress: 0,
      attempts: 0,
    };
    if (file.size > options.maxFileSizeBytes) {
      row.status = 'failed';
      row.progress = 100;
      row.errorCode = 'FILE_TOO_LARGE';
      row.errorMessage = 'FILE_TOO_LARGE';
      oversized.push(row);
    } else {
      valid.push(row);
    }
  }
  return { valid, oversized };
}

export function createUploadBatches(
  files: BulkUploadFileResult[],
  options: Pick<CreateUploadBatchesOptions, 'maxFilesPerBatch' | 'maxBytesPerBatch'>
): BulkUploadBatchPlan[] {
  const maxFiles = Math.max(1, options.maxFilesPerBatch);
  const maxBytes = Math.max(1, options.maxBytesPerBatch);
  const batches: BulkUploadBatchPlan[] = [];
  let current: BulkUploadFileResult[] = [];
  let currentBytes = 0;

  const flush = () => {
    if (!current.length) return;
    batches.push({ files: current, totalBytes: currentBytes });
    current = [];
    currentBytes = 0;
  };

  for (const row of files) {
    const size = row.file.size;
    // If a single file exceeds maxBytesPerBatch but passed per-file size checks,
    // put it in its own batch (backend may still reject REQUEST_TOO_LARGE).
    const wouldExceedCount = current.length >= maxFiles;
    const wouldExceedBytes = current.length > 0 && currentBytes + size > maxBytes;
    if (wouldExceedCount || wouldExceedBytes) {
      flush();
    }
    current.push(row);
    currentBytes += size;
    if (current.length >= maxFiles || currentBytes >= maxBytes) {
      flush();
    }
  }
  flush();
  return batches;
}
