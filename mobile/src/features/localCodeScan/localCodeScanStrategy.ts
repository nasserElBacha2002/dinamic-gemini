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
import { parseStoredProductResults } from '../../core/storedProductResults';
import {
  serializeProductRejections,
  type ProductLabelRejection,
} from '../../core/productLabelRejection';
import { applyPositionScan, getActivePosition, hydratePositionSessionFromDrafts } from './activePositionStore';
import type { ActivePositionState } from '../../core/positionLabelPayload';
import { parseDinamicPositionPayload } from '../../core/positionLabelPayload';
import type { LocalLabelProfileResolver } from '../offlineRecognition/localLabelProfileResolver';
import { runProfileAwareLocalScan } from './profileAwareLocalScan';

/** Must cover native multipass (full + tiles + zoom crops). */
export const LOCAL_CODE_SCAN_TIMEOUT_MS = 22_000;
export const LOCAL_CODE_SCAN_CONCURRENCY = 1;
export const LOCAL_SCAN_STALE_MS = 60_000;
export const LOCAL_SCAN_OWNER = 'js-local-code-scan';

export { parseStoredProductResults } from '../../core/storedProductResults';

export interface LocalCodeScanStrategyDeps {
  readonly drafts: LocalDetectionDraftRepository;
  readonly reporter?: ObservabilityReporter | null;
  readonly detect?: typeof detectLocalBarcodes;
  readonly evaluateCapability?: typeof evaluateLocalCodeScanCapability;
  readonly nowMs?: () => number;
  readonly timeoutMs?: number;
  readonly onActivePositionChanged?: (
    captureSessionId: string,
    state: ActivePositionState,
  ) => Promise<void>;
  readonly profileResolver?: LocalLabelProfileResolver | null;
}

function freezePositionSnapshotJson(captureSessionId: string): string | null {
  const active = getActivePosition(captureSessionId);
  return active ? JSON.stringify(active) : null;
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
  readonly inventoryId?: string | null;
  readonly aisleId?: string | null;
  readonly recognitionContext?: 'ONLINE' | 'OFFLINE';
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

function draftStatusFromConsolidation(
  status: ReturnType<typeof consolidateCodeDetections>['status'],
  parsedError?: string | null,
): LocalDetectionDraftStatus {
  switch (status) {
    case 'RESOLVED':
    case 'RESOLVED_MULTI':
    case 'MISSING_QUANTITY':
      return 'RESOLVED';
    case 'NO_DETECTIONS':
      return 'UNRESOLVED';
    case 'NO_VALID_CODE':
      return parsedError === 'PLAIN_UNVERIFIED_PAYLOAD' ||
        parsedError === 'POSITION_LABEL_DETECTED'
        ? 'DETECTED_UNVERIFIED'
        : 'INVALID';
    case 'MULTIPLE_DISTINCT_CODES':
    case 'QUANTITY_CONFLICT':
      return 'AMBIGUOUS';
    default:
      return 'FAILED';
  }
}

/**
 * Shadow-mode local CODE_SCAN. Awaited before upload eligibility; never fails upload.
 */
export class LocalCodeScanStrategy {
  private active = 0;
  private readonly waiters: Array<() => void> = [];
  private generation = 0;
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

  /** Recover drafts left in SCANNING after process death. */
  async recoverStaleDrafts(): Promise<number> {
    const cutoff = new Date(this.nowMs() - LOCAL_SCAN_STALE_MS).toISOString();
    return this.deps.drafts.recoverStaleScanning(cutoff);
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
        scanOwner: null,
        scanGeneration: 0,
        comparisonStatus: 'SKIPPED',
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
        scanOwner: null,
        scanGeneration: 0,
        comparisonStatus: capability === 'DISABLED' ? 'SKIPPED' : 'PENDING',
      });
      emitObservability(this.deps.reporter, {
        name: 'local_scan_failed',
        sessionId: input.captureSessionId,
        clientFileId: input.clientFileId ?? undefined,
        attributes: {
          error_code: capability,
          detector_version: LOCAL_CODE_DETECTOR_VERSION,
        },
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
        scanGeneration: ++this.generation,
        comparisonStatus: 'PENDING',
      });
      return 'FAILED';
    }

    const scanGeneration = ++this.generation;
    await this.deps.drafts.upsertDraft({
      capturePhotoId: input.capturePhotoId,
      captureSessionId: input.captureSessionId,
      clientFileId: input.clientFileId,
      status: 'PENDING',
      parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
      detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
      preparedAssetFingerprint: input.preparedAssetFingerprint,
      candidateCount: 0,
      scanOwner: LOCAL_SCAN_OWNER,
      scanGeneration,
      comparisonStatus: 'PENDING',
    });

    await this.acquireSlot();
    const started = this.nowMs();
    emitObservability(this.deps.reporter, {
      name: 'local_scan_started',
      sessionId: input.captureSessionId,
      clientFileId: input.clientFileId ?? undefined,
      attributes: {
        detector_version: LOCAL_CODE_DETECTOR_VERSION,
        parser_version: LABEL_PAYLOAD_PARSER_VERSION,
        scan_generation: scanGeneration,
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
        scanOwner: LOCAL_SCAN_OWNER,
        scanGeneration,
        comparisonStatus: 'PENDING',
      });

      const candidates = await withTimeout(this.detect(input.preparedUri), this.timeoutMs);
      const offline = input.recognitionContext === 'OFFLINE';
      const profileAware = await runProfileAwareLocalScan({
        candidates,
        inventoryId: input.inventoryId ?? null,
        aisleId: input.aisleId ?? null,
        resolver: this.deps.profileResolver ?? null,
        offline,
      });
      let consolidated = profileAware.consolidation;
      if (profileAware.profileMissing && offline) {
        await this.deps.drafts.upsertDraft({
          capturePhotoId: input.capturePhotoId,
          captureSessionId: input.captureSessionId,
          clientFileId: input.clientFileId,
          status: 'FAILED',
          parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
          detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
          preparedAssetFingerprint: input.preparedAssetFingerprint,
          errorCode: 'SUPPLIER_LABEL_PROFILE_NOT_AVAILABLE_OFFLINE',
          candidateCount: candidates.length,
          scanOwner: LOCAL_SCAN_OWNER,
          scanGeneration,
          comparisonStatus: 'PENDING',
          recognitionProfileSnapshotJson: JSON.stringify(profileAware.recognitionSnapshot),
          recognitionContext: input.recognitionContext ?? null,
        });
        return 'FAILED';
      }
      if (profileAware.ambiguous) {
        await this.deps.drafts.upsertDraft({
          capturePhotoId: input.capturePhotoId,
          captureSessionId: input.captureSessionId,
          clientFileId: input.clientFileId,
          status: 'AMBIGUOUS',
          parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
          detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
          preparedAssetFingerprint: input.preparedAssetFingerprint,
          errorCode: 'AMBIGUOUS_LABEL_KIND',
          candidateCount: candidates.length,
          scanOwner: LOCAL_SCAN_OWNER,
          scanGeneration,
          comparisonStatus: 'PENDING',
          recognitionProfileSnapshotJson: JSON.stringify(profileAware.recognitionSnapshot),
          recognitionContext: input.recognitionContext ?? null,
        });
        return 'AMBIGUOUS';
      }
      // Supplier ITEM identity can resolve when Dinamic consolidator has no D1.
      if (
        !consolidated.d1Mode &&
        profileAware.supplierItem?.status === 'VALID' &&
        consolidated.productResults.length === 0
      ) {
        const sid = profileAware.supplierItem.labelId || profileAware.supplierItem.sku || '';
        const qty = profileAware.supplierItem.quantity;
        consolidated = {
          ...consolidated,
          status: qty == null ? 'MISSING_QUANTITY' : 'RESOLVED',
          internalCode: profileAware.supplierItem.sku || sid || null,
          quantity: qty,
          productResults: [
            {
              labelId: profileAware.supplierItem.labelId || sid,
              internalCode: profileAware.supplierItem.sku || sid,
              // ProductLabelResult.quantity is required; 0 means missing for SUPPLIER format.
              quantity: qty ?? 0,
              formatVersion: 'SUPPLIER',
              checksum: '',
              validationStatus: 'VALID',
              selectedIndex: 0,
              duplicateDetectionCount: 1,
              rawPayload: profileAware.supplierItem.rawPayload,
              normalizedPayload: profileAware.supplierItem.normalizedPayload,
            },
          ],
        };
      }
      const parsedError =
        consolidated.parsed?.status === 'INVALID' ? consolidated.parsed.errorCode : null;
      let status = draftStatusFromConsolidation(consolidated.status, parsedError);
      if (
        status === 'UNRESOLVED' ||
        status === 'INVALID' ||
        status === 'DETECTED_UNVERIFIED'
      ) {
        if (profileAware.supplierItem?.status === 'VALID') {
          status = 'RESOLVED';
        } else if (
          profileAware.supplierItem == null &&
          profileAware.supplierPosition == null &&
          candidates.length > 0
        ) {
          status = 'UNRESOLVED';
        }
      }
      const processingMs = Math.max(0, Math.round(this.nowMs() - started));
      const selectedRaw =
        consolidated.selectedIndex != null
          ? candidates[consolidated.selectedIndex]?.rawValue
          : candidates[0]?.rawValue;

      const sessionDrafts = await this.deps.drafts.listForSession(input.captureSessionId);
      hydratePositionSessionFromDrafts(input.captureSessionId, sessionDrafts);

      // Resolve POSITION independently of products (same photo may contain both).
      const activeBefore = getActivePosition(input.captureSessionId);
      let appliedPosition: ActivePositionState | null = null;
      let duplicatePosition = false;
      let positionRaw =
        consolidated.positionRawPayload ??
        candidates.find((c) => parseDinamicPositionPayload(c.rawValue) != null)?.rawValue ??
        null;
      if (!positionRaw && profileAware.supplierPosition?.status === 'VALID') {
        const posId =
          profileAware.supplierPosition.positionId ||
          profileAware.supplierPosition.normalizedPayload ||
          '';
        const sideRaw = (profileAware.supplierPosition.side || '').toUpperCase();
        const side =
          sideRaw === 'LEFT' || sideRaw === 'RIGHT' ? (sideRaw as 'LEFT' | 'RIGHT') : null;
        const levelRaw = profileAware.supplierPosition.level;
        const levelNum =
          levelRaw != null && levelRaw !== ''
            ? Number.parseInt(String(levelRaw), 10)
            : null;
        positionRaw = profileAware.supplierPosition.rawPayload;
        appliedPosition = {
          labelId: posId,
          positionLabelId: posId,
          displayName: posId,
          canonicalKey: posId,
          pallet: profileAware.supplierPosition.pallet,
          side,
          level: Number.isFinite(levelNum as number) ? (levelNum as number) : null,
          markerIndex: null,
          markerTotal: null,
          formattedMarker: null,
          rawPayload: profileAware.supplierPosition.rawPayload,
          sourcePayload: profileAware.supplierPosition.rawPayload,
          validationStatus: 'STRUCTURALLY_VALID_UNVERIFIED',
          signature: null,
          keyVersion: null,
        };
        if (this.deps.onActivePositionChanged && appliedPosition.labelId) {
          await this.deps.onActivePositionChanged(input.captureSessionId, appliedPosition);
        }
      }
      if (positionRaw && !appliedPosition) {
        const positionResult = applyPositionScan(input.captureSessionId, positionRaw);
        if (positionResult.kind === 'applied' || positionResult.kind === 'duplicate') {
          appliedPosition = positionResult.state;
          duplicatePosition = positionResult.kind === 'duplicate';
        }
      }
      if (appliedPosition && !duplicatePosition && this.deps.onActivePositionChanged && positionRaw) {
        await this.deps.onActivePositionChanged(input.captureSessionId, appliedPosition);
      }

      const positionSnapshotJson = freezePositionSnapshotJson(input.captureSessionId);
      const positionDetected = Boolean(appliedPosition);

      // Session-scoped label_id dedupe (count once).
      const seenLabelIds = new Set<string>();
      for (const d of sessionDrafts) {
        if (d.capture_photo_id === input.capturePhotoId) continue;
        for (const p of parseStoredProductResults(d.product_results_json)) {
          if (p.labelId) seenLabelIds.add(p.labelId);
        }
        if (d.label_id) seenLabelIds.add(d.label_id);
      }

      let products = [...consolidated.productResults];
      const rejections: ProductLabelRejection[] = [...consolidated.rejections];
      let duplicateLabels = 0;
      if (products.length > 0) {
        const kept: typeof products = [];
        for (const p of products) {
          if (seenLabelIds.has(p.labelId)) {
            duplicateLabels += 1;
            rejections.push({
              labelId: p.labelId,
              validationStatus: 'DUPLICATE_LABEL',
              reason: 'session_label_already_counted',
              detectionIndex: p.selectedIndex,
              rawValuePreview: p.rawPayload.slice(0, 48),
            });
            continue;
          }
          seenLabelIds.add(p.labelId);
          kept.push(p);
        }
        products = kept;
      }

      const productResultsJson =
        products.length > 0
          ? JSON.stringify(
              products.map((p) => ({
                labelId: p.labelId,
                internalCode: p.internalCode,
                quantity: p.quantity,
                validationStatus: p.validationStatus,
                formatVersion: p.formatVersion,
                selectedIndex: p.selectedIndex,
              })),
            )
          : null;
      const rejectionsJson = serializeProductRejections(rejections);

      const primary = products[0] ?? null;
      const d1Mode = consolidated.d1Mode;
      // In D1 MODE never persist legacy scalar codes (blocks CSV revival).
      const persistInternalCode = d1Mode
        ? primary?.internalCode ?? null
        : primary?.internalCode ?? consolidated.internalCode;
      const supplierMissingQty =
        primary?.formatVersion === 'SUPPLIER' &&
        profileAware.supplierItem?.quantity == null;
      const persistQuantity = supplierMissingQty
        ? null
        : d1Mode
          ? primary?.quantity ?? null
          : primary?.quantity ?? consolidated.quantity;
      const isPositionOnly =
        positionDetected && products.length === 0 && (d1Mode || consolidated.status === 'NO_VALID_CODE');

      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: isPositionOnly ? 'DETECTED_UNVERIFIED' : status,
        rawValueHash: selectedRaw ? hashPayloadFingerprint(selectedRaw) : null,
        internalCode: persistInternalCode,
        quantity: persistQuantity,
        labelId: primary?.labelId ?? null,
        productResultsJson,
        rejectionsJson,
        positionDetected,
        quantityStatus:
          consolidated.status === 'MISSING_QUANTITY' || supplierMissingQty
            ? 'MISSING'
            : persistQuantity != null
              ? 'PRESENT'
              : consolidated.status === 'NO_DETECTIONS'
                ? null
                : consolidated.parsed?.quantityStatus ?? null,
        detectedFormat:
          consolidated.parsed?.status === 'VALID' || consolidated.parsed?.status === 'INVALID'
            ? consolidated.parsed.format
            : primary?.formatVersion === 'SUPPLIER'
              ? 'SUPPLIER'
              : null,
        detectedSymbology:
          consolidated.selectedIndex != null
            ? candidates[consolidated.selectedIndex]?.symbology ?? null
            : candidates[0]?.symbology ?? null,
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        candidateCount: candidates.length,
        errorCode: duplicatePosition && products.length === 0
          ? 'POSITION_LABEL_DUPLICATE'
          : isPositionOnly
            ? 'POSITION_LABEL_DETECTED'
            : status === 'AMBIGUOUS'
              ? consolidated.status
              : status === 'INVALID' || status === 'DETECTED_UNVERIFIED'
                ? parsedError ??
                  (d1Mode && products.length === 0
                    ? 'D1_CANDIDATES_FAILED'
                    : consolidated.warnings.includes('D1_CANDIDATES_FAILED')
                      ? 'D1_CANDIDATES_FAILED'
                      : 'NO_VALID_CODE')
                : status === 'UNRESOLVED'
                  ? 'NO_DETECTIONS'
                  : null,
        processingMs,
        scanOwner: null,
        scanGeneration,
        comparisonStatus: 'PENDING',
        positionSnapshotJson,
        recognitionProfileSnapshotJson: profileAware.recognitionSnapshot
          ? JSON.stringify(profileAware.recognitionSnapshot)
          : null,
        recognitionContext: input.recognitionContext ?? null,
      });

      const validLabelIds = products.map((p) => p.labelId);
      const rejectedLabelIds = rejections
        .map((r) => r.labelId)
        .filter((id): id is string => Boolean(id));
      emitObservability(this.deps.reporter, {
        name: 'local_scan_multilabel_trace',
        sessionId: input.captureSessionId,
        clientFileId: input.clientFileId ?? undefined,
        durationMs: processingMs,
        attributes: {
          capture_photo_id: input.capturePhotoId,
          raw_codes_detected_count: candidates.length,
          raw_codes_json: JSON.stringify(
            candidates.map((c) => ({
              format: c.symbology,
              raw_preview: c.rawValue.slice(0, 64),
              bounding_box: c.boundingBox ?? null,
            })),
          ),
          position_candidates_count: consolidated.positionRawPayload ? 1 : 0,
          product_d1_candidates_count: candidates.filter((c) => {
            const v = c.rawValue.trim().toUpperCase();
            return v.startsWith('D1|') || /^D\d+\|/.test(v);
          }).length,
          legacy_candidates_count: candidates.filter((c) => {
            const v = c.rawValue;
            return v.includes('|') && !v.toUpperCase().startsWith('D1|') && !v.includes('"type"');
          }).length,
          d1_mode: d1Mode,
          d1_valid_count: products.length,
          d1_invalid_count: consolidated.rejections.length,
          valid_label_ids: validLabelIds.join(','),
          rejected_label_ids: rejectedLabelIds.join(','),
          consolidated_product_results_count: consolidated.productResults.length,
          strategy_product_results_count: products.length,
          stored_product_results_count: products.length,
          rejections_count: rejections.length,
          duplicate_labels: duplicateLabels,
          duplicate_position: duplicatePosition,
          consolidation_status: consolidated.status,
        },
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
          capture_photo_id: input.capturePhotoId,
          codes_detected: candidates.length,
          position_candidates: consolidated.positionRawPayload ? 1 : 0,
          product_candidates: consolidated.productResults.length,
          d1_valid: products.length,
          d1_invalid: consolidated.rejections.length,
          d1_mode: d1Mode,
          products_emitted: products.length,
          duplicate_labels: duplicateLabels,
          duplicate_position: duplicatePosition,
          rejections_count: rejections.length,
          active_position_before: activeBefore?.labelId ?? null,
          position_detected: positionDetected,
          active_position_after: getActivePosition(input.captureSessionId)?.labelId ?? null,
          detected_symbology:
            (consolidated.selectedIndex != null
              ? candidates[consolidated.selectedIndex]?.symbology
              : candidates[0]?.symbology) ?? null,
        },
      });
      return isPositionOnly ? 'DETECTED_UNVERIFIED' : status;
    } catch (e) {
      const processingMs = Math.max(0, Math.round(this.nowMs() - started));
      const message = String(e);
      const timedOut = message.includes('LOCAL_SCAN_TIMEOUT');
      await this.deps.drafts.upsertDraft({
        capturePhotoId: input.capturePhotoId,
        captureSessionId: input.captureSessionId,
        clientFileId: input.clientFileId,
        status: timedOut ? 'FAILED' : 'FAILED_RETRYABLE',
        parserVersion: LABEL_PAYLOAD_PARSER_VERSION,
        detectorVersion: LOCAL_CODE_DETECTOR_VERSION,
        preparedAssetFingerprint: input.preparedAssetFingerprint,
        errorCode: timedOut ? 'LOCAL_SCAN_TIMEOUT' : 'LOCAL_SCAN_FAILED',
        candidateCount: 0,
        processingMs,
        scanOwner: null,
        scanGeneration,
        comparisonStatus: 'PENDING',
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
      return timedOut ? 'FAILED' : 'FAILED_RETRYABLE';
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

export type ShadowCompareResult =
  | 'MATCH_CODE_AND_QUANTITY'
  | 'MATCH_CODE_BOTH_QUANTITY_MISSING'
  | 'MATCH_CODE_LOCAL_QUANTITY_MISSING'
  | 'MATCH_CODE_REMOTE_QUANTITY_MISSING'
  | 'MATCH_CODE_QUANTITY_DIFFERENT'
  | 'CODE_MISMATCH'
  | 'LOCAL_ONLY'
  | 'REMOTE_ONLY'
  | 'BOTH_UNRESOLVED'
  | 'LOCAL_AMBIGUOUS'
  | 'REMOTE_AMBIGUOUS'
  | 'BOTH_AMBIGUOUS'
  | 'NOT_COMPARABLE';

/** @deprecated Use REMOTE_ONLY — kept for older draft rows. */
export type LegacyShadowCompareResult = ShadowCompareResult | 'SERVER_ONLY' | 'MATCH_CODE_QUANTITY_MISSING_LOCAL';

export function compareLocalVsServer(input: {
  readonly localInternalCode: string | null;
  readonly localQuantity: number | null;
  readonly localStatus: LocalDetectionDraftStatus;
  readonly serverInternalCode: string | null | undefined;
  readonly serverQuantity: number | null | undefined;
  readonly mappingReliable: boolean;
  readonly localAmbiguous?: boolean;
  readonly remoteAmbiguous?: boolean;
}): ShadowCompareResult {
  if (!input.mappingReliable) {
    return 'NOT_COMPARABLE';
  }
  const localAmbiguous =
    input.localAmbiguous === true || input.localStatus === 'AMBIGUOUS';
  const remoteAmbiguous = input.remoteAmbiguous === true;
  if (localAmbiguous && remoteAmbiguous) {
    return 'BOTH_AMBIGUOUS';
  }
  if (localAmbiguous) {
    return 'LOCAL_AMBIGUOUS';
  }
  if (remoteAmbiguous) {
    return 'REMOTE_AMBIGUOUS';
  }

  const localResolved =
    (input.localStatus === 'RESOLVED' || input.localStatus === 'DETECTED_UNVERIFIED') &&
    Boolean(input.localInternalCode);
  const serverResolved = Boolean(input.serverInternalCode);

  if (!localResolved && !serverResolved) {
    return 'BOTH_UNRESOLVED';
  }
  if (localResolved && !serverResolved) {
    return 'LOCAL_ONLY';
  }
  if (!localResolved && serverResolved) {
    return 'REMOTE_ONLY';
  }
  if (input.localInternalCode !== input.serverInternalCode) {
    return 'CODE_MISMATCH';
  }
  if (input.localQuantity == null && input.serverQuantity == null) {
    return 'MATCH_CODE_BOTH_QUANTITY_MISSING';
  }
  if (input.localQuantity == null && input.serverQuantity != null) {
    return 'MATCH_CODE_LOCAL_QUANTITY_MISSING';
  }
  if (input.localQuantity != null && input.serverQuantity == null) {
    return 'MATCH_CODE_REMOTE_QUANTITY_MISSING';
  }
  if (
    input.localQuantity != null &&
    input.serverQuantity != null &&
    input.localQuantity !== input.serverQuantity
  ) {
    return 'MATCH_CODE_QUANTITY_DIFFERENT';
  }
  return 'MATCH_CODE_AND_QUANTITY';
}
