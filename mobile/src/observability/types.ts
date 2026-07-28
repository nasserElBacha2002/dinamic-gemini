/** Phase 0 — mobile upload/process observability types. */

export type ObservabilityAttributeValue = string | number | boolean | null;

export interface ObservabilityEvent {
  readonly name: string;
  readonly timestamp: string;
  readonly sessionId?: string;
  readonly localJobId?: string;
  readonly serverJobId?: string;
  readonly clientFileId?: string;
  readonly batchId?: string;
  readonly attemptId?: string;
  readonly durationMs?: number;
  readonly attributes?: Readonly<Record<string, ObservabilityAttributeValue>>;
}

export interface ObservabilityReporter {
  emit(event: ObservabilityEvent): void | Promise<void>;
}

export type NormalizedNetworkType = 'wifi' | 'cellular' | 'ethernet' | 'unknown' | 'offline';

export type ObservabilityErrorCode =
  | 'PREPARE_READ_FAILED'
  | 'PREPARE_CONVERSION_FAILED'
  | 'PREPARE_RESIZE_FAILED'
  | 'PREPARE_FAILED'
  | 'UPLOAD_TIMEOUT'
  | 'UPLOAD_NETWORK_ERROR'
  | 'UPLOAD_ABORTED'
  | 'UPLOAD_HTTP_4XX'
  | 'UPLOAD_HTTP_5XX'
  | 'UPLOAD_LIMIT_EXCEEDED'
  | 'UPLOAD_RETRYABLE'
  | 'PROCESS_REQUEST_FAILED'
  | 'JOB_POLL_FAILED'
  | 'JOB_TERMINAL_FAILED'
  | 'QUEUE_RESTORE_FAILED'
  | 'UNKNOWN_ERROR';
