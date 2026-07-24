import { consolidateCodeDetections } from '../../core/codeDetectionConsolidator';
import type { PreparationProcessingMode } from '../../core/imagePreparationPolicy';
import { LABEL_PAYLOAD_PARSER_VERSION } from '../../core/labelPayload';
import { hashPayloadFingerprint } from '../../core/payloadFingerprint';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftStatus,
} from '../../database/repositories/localDetectionDraftRepository';
import { emitObservability, type ObservabilityReporter } from '../../observability';
import {
  detectLocalBarcodes,
  evaluateLocalCodeScanCapability,
  LOCAL_CODE_DETECTOR_VERSION,
} from './localCodeDetector';

export const LOCAL_CODE_SCAN_TIMEOUT_MS = 10_000;
export const LOCAL_CODE_SCAN_CONCURRENCY = 1;

export type ShadowCompareResult =
  | 'MATCH_CODE_AND_QUANTITY'
  | 'MATCH_CODE_QUANTITY_MISSING_LOCAL'
  | 'MATCH_CODE_QUANTITY_DIFFERENT'
  | 'CODE_MISMATCH'
  | 'LOCAL_ONLY'
  | 'SERVER_ONLY'
  | 'BOTH_UNRESOLVED'
  | 'NOT_COMPARABLE';

export interface LocalCodeScanStrategyDeps {
  readonly drafts: LocalDetectionDraftRepository;
  readonly reporter?: ObservabilityReporter | null;
  readonly detect?: typeof detectLocalBarcodes;
  readonly evaluateCapability?: typeof evaluateLocalCodeScanCapability;
  readonly nowMs?: () => number;
  readonly timeoutMs?: number;
}

export interface LocalCodeScanInput {
  readonly capturePhotoId: string;
  readonly captureSessionId: string;
  readonly clientFileId: string | null;
  readonly preparedUri: string;
  readonly preparedAssetFingerprint: string;
  readonly processingMode: PreparationProcessingMode;
  readonly flagEnabled: boolean;
  readonly cancelRequested?: boolean;
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('LOCAL_SCAN_TIMEOUT')), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

function sanitizePreview(raw: string): string {
  // Length-capped, strip ASCII controls — never log full payload.
  let out = '';
  for (let i = 0; i < raw.length && out.length < 32; i += 1) {
    const c = raw.charCodeAt(i);
    if (c >= 0x20 && c !== 0x7f) {
      out += raw[i]!;
    }
  }
  return out;
}

function draftStatusFromConsolidation(
  status: ReturnType<typeof consolidateCodeDetections>['status'],
): LocalDetectionDraftStatus {
  switch (status) {
    case 'RESOLVED':
    case 'MISSING_QUANTITY':
      return 'RESOLVED';
    case 'NO_DETECTIONS':
      return 'UNRESOLVED';
    case 'NO_VALID_CODE':
      return 'INVALID';
    case 'MULTIPLE_DISTINCT_CODES':
    case 'QUANTITY_CONFLICT':
      return 'AMBIGUOUS';
    default:
      return 'FAILED';
  }
}

/**
 * Shadow-mode local CODE_SCAN. Never blocks upload; never creates positions.
 */
export class LocalCodeScanStrategy {
  private active = 0;
  private readonly waiters: Array<() => void> = [];
  private readonly detect: typeof detectLocalBarcodes;
  private readonly evaluateCapability: typeof evaluateLocalCodeScanCapability;
  private readonly nowMs: () => number;
  private readonly timeoutMs: number;

  constructor(private readonly deps: LocalCodeScanStrategyDeps) {
    this.detect = deps.detect ?? detectLocalBarcodes;
    this.evaluateCapability = deps.evaluateCapability ?? evaluateLocalCodeScanCapability;
    this.nowMs = deps.nowMs ?? (() => Date.now());
    this.timeoutMs = deps.timeoutMs ?? LOCAL_CODE_SCAN_TIMEOUT_MS;
  }

  async execute(input: LocalCodeScanInput): Promise<LocalDetectionDraftStatus> {
    if (input.processingMode !== 'CODE_SCAN') {
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: 'NOT_APPLICABLE',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        candidateCount: 0,
      });
      return 'NOT_APPLICABLE';
    }

    const capability = await this.evaluateCapability({ flagEnabled: input.flagEnabled });
    if (capability !== 'SUPPORTED') {
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: capability === 'DISABLED' ? 'NOT_APPLICABLE' : 'FAILED',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        errorCode: capability,
        candidateCount: 0,
      });
      return capability === 'DISABLED' ? 'NOT_APPLICABLE' : 'FAILED';
    }

    if (input.cancelRequested) {
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: 'FAILED',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        errorCode: 'CANCELLED',
        candidateCount: 0,
      });
      return 'FAILED';
    }

    await this.acquireSlot();
    const started = this.nowMs();
    emitObservability(this.deps.reporter, {
      name: 'local_scan_started',
      sessionId: input.captureSessionId,
      clientFileId: input.clientFileId ?? undefined,
      attributes: {
        detector_version: LOCAL_CODE_DETECTOR_VERSION,
        parser_version: LABEL_PAYLOAD_PARSER_VERSION,
      },
    });

    try {
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: 'SCANNING',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        candidateCount: 0,
      });

      const candidates = await withTimeout(this.detect(input.preparedUri), this.timeoutMs);
      const consolidated = consolidateCodeDetections(candidates);
      const status = draftStatusFromConsolidation(consolidated.status);
      const processingMs = Math.max(0, Math.round(this.nowMs() - started));
      const selectedRaw =
        consolidated.selectedIndex != null
          ? candidates[consolidated.selectedIndex]?.rawValue
          : candidates[0]?.rawValue;

      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status,
        rawValueHash: selectedRaw ? hashPayloadFingerprint(selectedRaw) : null,
        rawValuePreview: selectedRaw ? sanitizePreview(selectedRaw) : null,
        internalCode: consolidated.internalCode,
        quantity: consolidated.quantity,
        quantityStatus:
          consolidated.status === 'MISSING_QUANTITY'
            ? 'MISSING'
            : consolidated.quantity != null
              ? 'PRESENT'
              : consolidated.status === 'NO_DETECTIONS'
                ? null
                : consolidated.parsed?.quantityStatus ?? null,
        detectedFormat:
          consolidated.parsed?.status === 'VALID' || consolidated.parsed?.status === 'INVALID'
            ? consolidated.parsed.format
            : null,
        detectedSymbology:
          consolidated.selectedIndex != null
            ? candidates[consolidated.selectedIndex]?.symbology ?? null
            : candidates[0]?.symbology ?? null,
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        candidateCount: candidates.length,
        errorCode:
          status === 'AMBIGUOUS'
            ? consolidated.status
            : status === 'INVALID'
              ? consolidated.parsed?.status === 'INVALID'
                ? consolidated.parsed.errorCode
                : 'NO_VALID_CODE'
              : status === 'UNRESOLVED'
                ? 'NO_DETECTIONS'
                : null,
        processingMs,
      });

      const eventName =
        status === 'AMBIGUOUS'
          ? 'local_scan_ambiguous'
          : status === 'FAILED'
            ? 'local_scan_failed'
            : 'local_scan_completed';
      emitObservability(this.deps.reporter, {
        name: eventName,
        sessionId: input.captureSessionId,
        clientFileId: input.clientFileId ?? undefined,
        durationMs: processingMs,
        attributes: {
          local_scan_ms: processingMs,
          local_scan_candidate_count: candidates.length,
          local_scan_status: status,
          consolidation_status: consolidated.status,
          detector_version: LOCAL_CODE_DETECTOR_VERSION,
          parser_version: LABEL_PAYLOAD_PARSER_VERSION,
          detected_symbology:
            (consolidated.selectedIndex != null
              ? candidates[consolidated.selectedIndex]?.symbology
              : candidates[0]?.symbology) ?? null,
        },
      });
      return status;
    } catch (e) {
      const processingMs = Math.max(0, Math.round(this.nowMs() - started));
      const message = String(e);
      const timedOut = message.includes('LOCAL_SCAN_TIMEOUT');
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: 'FAILED',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        errorCode: timedOut ? 'LOCAL_SCAN_TIMEOUT' : 'LOCAL_SCAN_FAILED',
        candidateCount: 0,
        processingMs,
      });
      emitObservability(this.deps.reporter, {
        name: timedOut ? 'local_scan_timeout' : 'local_scan_failed',
        sessionId: input.captureSessionId,
        clientFileId: input.clientFileId ?? undefined,
        durationMs: processingMs,
        attributes: {
          local_scan_ms: processingMs,
          error_code: timedOut ? 'LOCAL_SCAN_TIMEOUT' : 'LOCAL_SCAN_FAILED',
        },
      });
      return 'FAILED';
    } finally {
      this.releaseSlot();
    }
  }

  private acquireSlot(): Promise<void> {
    if (this.active < LOCAL_CODE_SCAN_CONCURRENCY) {
      this.active += 1;
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      this.waiters.push(() => {
        this.active += 1;
        resolve();
      });
    });
  }

  private releaseSlot(): void {
    this.active = Math.max(0, this.active - 1);
    const next = this.waiters.shift();
    if (next) {
      next();
    }
  }
}

export function compareLocalVsServer(input: {
  readonly localInternalCode: string | null;
  readonly localQuantity: number | null;
  readonly localStatus: LocalDetectionDraftStatus;
  readonly serverInternalCode: string | null | undefined;
  readonly serverQuantity: number | null | undefined;
  readonly mappingReliable: boolean;
}): ShadowCompareResult {
  if (!input.mappingReliable) {
    return 'NOT_COMPARABLE';
  }
  const localResolved =
    input.localStatus === 'RESOLVED' && Boolean(input.localInternalCode);
  const serverResolved = Boolean(input.serverInternalCode);

  if (!localResolved && !serverResolved) {
    return 'BOTH_UNRESOLVED';
  }
  if (localResolved && !serverResolved) {
    return 'LOCAL_ONLY';
  }
  if (!localResolved && serverResolved) {
    return 'SERVER_ONLY';
  }
  if (input.localInternalCode !== input.serverInternalCode) {
    return 'CODE_MISMATCH';
  }
  if (input.localQuantity == null && input.serverQuantity != null) {
    return 'MATCH_CODE_QUANTITY_MISSING_LOCAL';
  }
  if (
    input.localQuantity != null &&
    input.serverQuantity != null &&
    input.localQuantity !== input.serverQuantity
  ) {
    return 'MATCH_CODE_QUANTITY_DIFFERENT';
  }
  if (
    input.localQuantity != null &&
    input.serverQuantity != null &&
    input.localQuantity === input.serverQuantity
  ) {
    return 'MATCH_CODE_AND_QUANTITY';
  }
  // Codes match; both missing quantity or local missing already handled.
  return 'MATCH_CODE_QUANTITY_MISSING_LOCAL';
}
