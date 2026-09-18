import * as FileSystem from 'expo-file-system';

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import { canonicalizeDraftsByPhoto } from '../../database/repositories/localDetectionDraftRepository';
import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import { createId } from '../../shared/createId';
import type { AisleService } from '../aisles/aisleService';
import { CaptureFreezeService } from '../capture/captureFreezeService';
import type { ExportPrepQueue } from '../exportPrep/exportPrepQueue';
import type { LocalCsvExportService } from '../localCsv/localCsvExportService';
import type { LocalLabelProfileResolver } from '../offlineRecognition/localLabelProfileResolver';
import type { SessionArtifactPurgeCoordinator } from '../exportPrep/sessionArtifactPurgeCoordinator';
import {
  AUTHORIZED_BENCHMARK_CLIENT_ID,
  AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
  BENCHMARK_NAMESPACE_PREFIX,
  BENCHMARK_RECOGNITION_HOST_INVENTORY_ID,
} from './authorizedIds';
import { evaluateBenchmarkGate } from './benchmarkGate';
import {
  assertDeletableBenchmarkPath,
  assertSessionOwnedByRun,
  buildBenchmarkAisleCode,
  buildBenchmarkAssetId,
  buildBenchmarkSessionId,
  createResourceRegistry,
  type BenchmarkResourceRegistry,
} from './benchmarkIsolation';
import {
  createBenchmarkMetricsSink,
  measureStage,
  monoNowMs,
  type BenchmarkMetricsSink,
} from './benchmarkMetrics';
import { classifyDraftOutcome, outcomeIsSuccess } from './benchmarkOutcomes';
import { runBenchmarkProfilePreflight } from './benchmarkProfilePreflight';
import {
  clearBenchmarkFixtures,
  registerBenchmarkFixture,
} from './benchmarkFixtureMap';
import {
  captureBenchmarkEnvironmentStart,
  finalizeBenchmarkEnvironment,
} from './benchmarkEnvironment';
import {
  buildDualCorrectnessRow,
  reconstructActualFromDraft,
  summarizeDualCorrectness,
  type DualCorrectnessRow,
} from './benchmarkDualCorrectness';
import { classifyScenarioKind } from './benchmarkFixtureOrder';
import {
  getNativeBarcodeScanConcurrencyStats,
  setNativeBarcodeScanConcurrency,
} from '../localCodeScan/localCodeDetector';

export type BenchmarkRunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'TIMEOUT';

export interface BenchmarkFixtureRef {
  readonly sequence: number;
  readonly fixtureId: string;
  readonly filename: string;
  readonly type: string;
  readonly sizeBytes: number;
  readonly width: number;
  readonly height: number;
  /** Absolute file:// URI inside benchmark sandbox (device). */
  readonly fileUri: string;
  /** Original manifest sequence before interleave (optional). */
  readonly originalSequence?: number;
  /** Manifest scenario kind when known (position/item/multi_*). */
  readonly scenarioKind?: string;
  /** Manifest labels_json for dual correctness expected side. */
  readonly labelsJson?: string | null;
  /** Manifest scenario string (e.g. position_single_valid). */
  readonly scenario?: string | null;
  readonly category?: string | null;
}

export interface BenchmarkCommand {
  readonly enabled: true;
  readonly benchmarkRunId: string;
  readonly mode: 'synthetic-inject' | 'media-store-replay';
  readonly clientId: string;
  readonly supplierId: string;
  readonly photos: number;
  readonly coldWarm: 'cold' | 'warm';
  readonly fixtures: readonly BenchmarkFixtureRef[];
  readonly skipUpload: true;
  readonly timeoutMs?: number;
  /**
   * Phase 4 experimental knob — strictly 1 or 2.
   * Controls LocalCodeScanStrategy + native ML Kit slots only.
   * Does NOT change ExportPrepQueue workers (always 1 for Phase 4 A/B).
   * Default 1 (production-safe). Does not change the app default unless command sets 2.
   */
  readonly scannerConcurrency?: 1 | 2;
  readonly fixtureOrderVersion?: string;
  readonly fixtureOrderSeed?: number;
}

export interface BenchmarkStatusDocument {
  readonly status: BenchmarkRunStatus;
  readonly benchmarkRunId: string;
  readonly updatedAtUtc: string;
  readonly terminalCount: number;
  readonly expectedCount: number;
  readonly pendingJobs: number;
  readonly errorCode: string | null;
  readonly errorDetail: string | null;
  readonly profile: Record<string, unknown> | null;
  readonly exportId: string | null;
  readonly sessionId: string | null;
  readonly metricsPath: string | null;
  /** Optional Phase 4 dual-correctness / concurrency extras. */
  readonly extras?: Record<string, unknown> | null;
}

export interface BenchmarkRunnerDeps {
  readonly environment: 'development' | 'staging' | 'production';
  readonly isDevelopment: boolean;
  readonly processId: string;
  readonly captureRepo: CaptureRepository;
  readonly catalogRepo: LocalCatalogRepository;
  readonly recognitionRepo: OfflineRecognitionConfigRepository;
  readonly draftRepo: LocalDetectionDraftRepository;
  readonly aisles: AisleService;
  readonly exportPrepQueue: ExportPrepQueue | null;
  readonly localCsvExport: LocalCsvExportService | null;
  readonly profileResolver: LocalLabelProfileResolver;
  readonly sessionPurge: SessionArtifactPurgeCoordinator | null;
  readonly documentDirectory: string;
  /** Optional: apply JS scan concurrency for Phase 4 A/B. */
  readonly localCodeScan?: import('../localCodeScan/localCodeScanStrategy').LocalCodeScanStrategy | null;
}

function emptyMarker(inventoryId: string, aisleId: string) {
  return {
    assetId: null,
    mediaStoreNumericId: null,
    dateAdded: null,
    dateModified: null,
    displayName: null,
    size: null,
    bucketId: null,
    inventoryId,
    aisleId,
  };
}

export class BenchmarkRunner {
  private running = false;

  constructor(private readonly deps: BenchmarkRunnerDeps) {}

  statusPath(runId: string): string {
    return `${this.deps.documentDirectory}${BENCHMARK_NAMESPACE_PREFIX}/${runId}/status.json`;
  }

  metricsPath(runId: string): string {
    return `${this.deps.documentDirectory}${BENCHMARK_NAMESPACE_PREFIX}/${runId}/events.jsonl`;
  }

  async writeStatus(doc: BenchmarkStatusDocument): Promise<void> {
    const path = this.statusPath(doc.benchmarkRunId);
    await FileSystem.writeAsStringAsync(path, JSON.stringify(doc, null, 2));
  }

  async run(command: BenchmarkCommand): Promise<BenchmarkStatusDocument> {
    if (this.running) {
      throw Object.assign(new Error('BENCHMARK_ALREADY_RUNNING'), {
        code: 'BENCHMARK_ALREADY_RUNNING',
      });
    }
    this.running = true;
    const runId = command.benchmarkRunId;
    const registry = createResourceRegistry(runId);
    const timeoutMs = command.timeoutMs ?? 15 * 60_000;
    let status: BenchmarkStatusDocument = {
      status: 'RUNNING',
      benchmarkRunId: runId,
      updatedAtUtc: new Date().toISOString(),
      terminalCount: 0,
      expectedCount: command.fixtures.length,
      pendingJobs: 0,
      errorCode: null,
      errorDetail: null,
      profile: null,
      exportId: null,
      sessionId: null,
      metricsPath: null,
    };

    try {
      const exclusive = await this.deps.captureRepo.findExclusiveCaptureSession();
      const gate = evaluateBenchmarkGate({
        environment: this.deps.environment,
        isDevelopment: this.deps.isDevelopment,
        commandEnabled: command.enabled === true,
        exclusiveSessionActive: exclusive != null,
      });
      if (!gate.ok) {
        status = {
          ...status,
          status: 'FAILED',
          errorCode: gate.reason,
          errorDetail: `gate:${gate.reason}`,
        };
        await this.writeStatus(status);
        return status;
      }

      if (command.mode !== 'synthetic-inject') {
        status = {
          ...status,
          status: 'FAILED',
          errorCode: 'MODE_NOT_SUPPORTED_IN_PRIMARY',
          errorDetail: 'media-store-replay is separate; primary mode is synthetic-inject',
        };
        await this.writeStatus(status);
        return status;
      }

      if (
        command.clientId !== AUTHORIZED_BENCHMARK_CLIENT_ID ||
        command.supplierId !== AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID
      ) {
        status = {
          ...status,
          status: 'FAILED',
          errorCode: 'UNAUTHORIZED_IDS',
          errorDetail: 'client/supplier mismatch',
        };
        await this.writeStatus(status);
        return status;
      }

      if (!this.deps.exportPrepQueue || !this.deps.localCsvExport) {
        status = {
          ...status,
          status: 'FAILED',
          errorCode: 'EXPORT_PIPELINE_DISABLED',
          errorDetail: 'exportPrepQueue or localCsvExport unavailable',
        };
        await this.writeStatus(status);
        return status;
      }

      await this.writeStatus(status);

      const preflight = await runBenchmarkProfilePreflight({
        catalog: this.deps.catalogRepo,
        recognitionRepo: this.deps.recognitionRepo,
        clientId: command.clientId,
        supplierRouteId: command.supplierId,
        hostInventoryId: BENCHMARK_RECOGNITION_HOST_INVENTORY_ID,
      });

      const sink = createBenchmarkMetricsSink({
        benchmarkRunId: runId,
        processId: this.deps.processId,
        resolvedClientSupplierId: preflight.resolvedClientSupplierId,
        resolvedProfileName: preflight.resolvedProfileName,
      });
      sink.emit({
        sessionId: null,
        photoId: null,
        sequence: null,
        fixtureId: null,
        stage: 'profile_preflight',
        monotonicStartMs: 0,
        durationMs: 0,
        inputBytes: null,
        outputBytes: null,
        queueDepth: null,
        workerConcurrency: null,
        executionContext: 'js',
        success: preflight.ok,
        outcome: null,
        errorCode: preflight.failureCode,
        resolvedClientSupplierId: preflight.resolvedClientSupplierId,
        resolvedProfileName: preflight.resolvedProfileName,
        extras: {
          itemProfileVersion: preflight.itemProfileVersion,
          positionProfileVersion: preflight.positionProfileVersion,
          snapshotResolved: preflight.snapshotResolved,
          fallbackUsed: preflight.fallbackUsed,
        },
      });

      status = {
        ...status,
        profile: {
          resolvedClientId: preflight.resolvedClientId,
          resolvedSupplierId: preflight.resolvedSupplierId,
          resolvedClientSupplierId: preflight.resolvedClientSupplierId,
          resolvedProfileName: preflight.resolvedProfileName,
          itemProfileVersion: preflight.itemProfileVersion,
          positionProfileVersion: preflight.positionProfileVersion,
          configurationSource: preflight.configurationSource,
          snapshotResolved: preflight.snapshotResolved,
          hostInventoryId: preflight.hostInventoryId,
          fallbackUsed: preflight.fallbackUsed,
        },
      };

      if (!preflight.ok) {
        status = {
          ...status,
          status: 'FAILED',
          errorCode: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
          errorDetail: `${preflight.failureCode}:${preflight.failureDetail}`,
        };
        await FileSystem.writeAsStringAsync(this.metricsPath(runId), sink.toJsonl());
        status = { ...status, metricsPath: this.metricsPath(runId) };
        await this.writeStatus(status);
        return status;
      }

      const pipelineStart = monoNowMs();
      const result = await this.runPipeline({
        command,
        preflight,
        sink,
        registry,
        timeoutMs,
        pipelineStart,
      });
      status = result;
      await FileSystem.writeAsStringAsync(this.metricsPath(runId), sink.toJsonl());
      status = { ...status, metricsPath: this.metricsPath(runId), updatedAtUtc: new Date().toISOString() };
      await this.writeStatus(status);
      return status;
    } catch (error) {
      const code =
        error && typeof error === 'object' && 'code' in error
          ? String((error as { code?: unknown }).code ?? 'ERROR')
          : 'ERROR';
      const message = error instanceof Error ? error.message.slice(0, 200) : 'unknown';
      status = {
        ...status,
        status: 'FAILED',
        errorCode: code,
        errorDetail: message,
        updatedAtUtc: new Date().toISOString(),
      };
      await this.writeStatus(status).catch(() => undefined);
      return status;
    } finally {
      this.running = false;
    }
  }

  private async runPipeline(input: {
    readonly command: BenchmarkCommand;
    readonly preflight: Awaited<ReturnType<typeof runBenchmarkProfilePreflight>>;
    readonly sink: BenchmarkMetricsSink;
    readonly registry: BenchmarkResourceRegistry;
    readonly timeoutMs: number;
    readonly pipelineStart: number;
  }): Promise<BenchmarkStatusDocument> {
    const { command, preflight, sink, registry, timeoutMs, pipelineStart } = input;
    const runId = command.benchmarkRunId;
    const hostInventoryId = preflight.hostInventoryId;
    registry.inventoryId = hostInventoryId;

    const scannerConcurrency: 1 | 2 =
      command.scannerConcurrency === 2 ? 2 : 1;
    // Phase 4 A/B: ExportPrepQueue workers are held constant at 2 for BOTH arms.
    // Local ML Kit scans only run inside processJob; with workers=1 the scanner
    // slot pool can never reach concurrency 2 (feed-starved). Holding workers=2
    // isolates the measured variable to scannerConcurrency (1 vs 2). Staging/hash
    // may overlap equally on both arms; only the scan slot/native ML Kit slots change.
    const exportPrepMaxWorkers = 2 as const;
    const queueForConcurrency = this.deps.exportPrepQueue;
    if (queueForConcurrency) {
      queueForConcurrency.setMaxWorkers(exportPrepMaxWorkers);
    }

    const nativeConc = await setNativeBarcodeScanConcurrency(scannerConcurrency).catch(() => ({
      configured: scannerConcurrency,
      applied: false as boolean,
      available: false as boolean,
    }));
    if (scannerConcurrency === 2 && (!nativeConc.available || !nativeConc.applied)) {
      throw Object.assign(
        new Error(
          'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE: C=2 requires native setBarcodeScanConcurrency; refusing silent fallback to C=1',
        ),
        { code: 'NATIVE_SCANNER_CONCURRENCY_UNAVAILABLE' },
      );
    }
    this.deps.localCodeScan?.setMaxConcurrency(scannerConcurrency);
    this.deps.localCodeScan?.clearRawDetectedPayloads?.();

    const envStart = await captureBenchmarkEnvironmentStart({
      totalFixtureBytes: command.fixtures.reduce((a, f) => a + f.sizeBytes, 0),
      fixtureCount: command.fixtures.length,
      exportPrepMaxWorkers,
      scannerConcurrency,
    });
    sink.emit({
      sessionId: null,
      stage: 'benchmark_environment_start',
      monotonicStartMs: monoNowMs(),
      durationMs: 0,
      executionContext: 'js',
      success: true,
      extras: {
        ...envStart,
        configuredConcurrency: scannerConcurrency,
        exportPrepMaxWorkers,
        scannerConcurrency,
        scanConcurrency: scannerConcurrency,
        nativeConcurrencyApplied: nativeConc.applied,
        nativeConcurrencyAvailable: nativeConc.available,
        activeConcurrency: queueForConcurrency?.getActiveWorkers() ?? 0,
        maxObservedExportPrepWorkers: queueForConcurrency?.getMaxObservedWorkers() ?? 0,
        maxObservedScannerConcurrency: this.deps.localCodeScan?.getMaxObservedConcurrency() ?? 0,
        fixtureOrderVersion: command.fixtureOrderVersion ?? null,
        fixtureOrderSeed: command.fixtureOrderSeed ?? null,
      },
    });

    const inventory = await this.deps.catalogRepo.getInventoryById(hostInventoryId);
    const inventoryName = inventory?.name ?? 'benchmark-host';

    const aisle = await this.deps.aisles.createLocal({
      inventoryId: hostInventoryId,
      code: buildBenchmarkAisleCode(runId),
      clientSupplierId: AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID,
    });
    registry.aisleId = aisle.id;

    // Fail if resolver would fall back to DINAMIC for this aisle
    this.deps.profileResolver.invalidate();
    const resolved = await this.deps.profileResolver.resolveForAisle(hostInventoryId, aisle.id);
    if (
      resolved.item.source !== 'SUPPLIER' ||
      resolved.position.source !== 'SUPPLIER' ||
      resolved.item.missingSupplierProfile ||
      resolved.position.missingSupplierProfile
    ) {
      throw Object.assign(new Error('BENCHMARK_PROFILE_PREFLIGHT_FAILED'), {
        code: 'BENCHMARK_PROFILE_PREFLIGHT_FAILED',
        detail: 'aisle resolution fell back or missing supplier profile',
      });
    }

    const sessionId = buildBenchmarkSessionId(runId);
    registry.sessionId = sessionId;

    const created = await this.deps.captureRepo.createSessionExclusive({
      id: sessionId,
      inventoryId: hostInventoryId,
      inventoryName: `BENCH/${inventoryName}`.slice(0, 80),
      aisleId: aisle.id,
      aisleName: aisle.code,
      marker: emptyMarker(hostInventoryId, aisle.id),
      uploadBatchId: `bench-batch-${runId}`,
    });
    if (!created.created && created.session.id !== sessionId) {
      throw Object.assign(new Error('EXCLUSIVE_SESSION_ACTIVE'), {
        code: 'EXCLUSIVE_SESSION_ACTIVE',
      });
    }

    await this.deps.captureRepo.updateSessionStatus(sessionId, 'active');
    await this.deps.captureRepo.updateSessionStatus(sessionId, 'finishing');
    await this.deps.captureRepo.updateSessionStatus(sessionId, 'review', true);
    await this.deps.captureRepo.setUploadPolicy(sessionId, 'MANUAL');
    await this.deps.captureRepo.setExportPackagingMode(sessionId, 'STAGING_REQUIRED');

    const images: GalleryImage[] = command.fixtures.map((fx) => ({
      assetId: buildBenchmarkAssetId(fx.sequence),
      uri: fx.fileUri.startsWith('file://') ? fx.fileUri : `file://${fx.fileUri}`,
      displayName: fx.filename,
      mimeType: 'image/jpeg',
      size: fx.sizeBytes,
      width: fx.width,
      height: fx.height,
      dateAdded: Math.floor(Date.now() / 1000) + fx.sequence,
      dateModified: Math.floor(Date.now() / 1000) + fx.sequence,
      bucketId: null,
      relativePath: null,
    }));

    await measureStage(
      sink,
      { sessionId, stage: 'admission', executionContext: 'js' },
      () => this.deps.captureRepo.upsertAdmittedPhotosWithSequences(sessionId, images, 'stable'),
    );

    const photos = await this.deps.captureRepo.listPhotos(sessionId);
    const admittedAtByPhotoId = new Map<string, number>();
    // Capture assigns contiguous sequence_number (1..n); fixture.sequence is manifest order
    // (e.g. 1,3,4). Correlate by asset_id which is built from fixture.sequence at admission.
    const fixtureByAssetId = new Map(
      command.fixtures.map((f) => [buildBenchmarkAssetId(f.sequence), f] as const),
    );
    for (const photo of photos) {
      const fx = fixtureByAssetId.get(photo.asset_id);
      if (fx) {
        registerBenchmarkFixture(runId, photo.id, fx.fixtureId);
      }
      admittedAtByPhotoId.set(photo.id, monoNowMs());
    }

    const postAdmitCounts = await this.deps.exportPrepQueue!.getCounts(sessionId).catch(() => null);
    sink.emit({
      sessionId,
      stage: 'queue_snapshot',
      monotonicStartMs: monoNowMs(),
      durationMs: 0,
      executionContext: 'js',
      success: true,
      queueDepth: postAdmitCounts?.pending ?? null,
      extras: {
        queueDepthAtEnd: postAdmitCounts?.pending ?? null,
        configuredWorkers: exportPrepMaxWorkers,
        exportPrepMaxWorkers,
        scannerConcurrency,
        when: 'post_admission',
      },
    });

    const freezeService = new CaptureFreezeService(this.deps.captureRepo);
    const freeze = await freezeService.freezeSession(sessionId, photos);

    const lastInjectMono = monoNowMs();
    const queue = this.deps.exportPrepQueue!;
    let maxQueueDepth = postAdmitCounts?.pending ?? 0;
    queue.setStageObserver({
      onStage: (evt) => {
        if (evt.queueDepth != null) {
          maxQueueDepth = Math.max(maxQueueDepth, evt.queueDepth);
        }
        sink.emit({
          sessionId,
          photoId: evt.photoId,
          sequence: evt.sequence,
          stage: evt.stage,
          monotonicStartMs: evt.monotonicStartMs,
          durationMs: evt.durationMs,
          inputBytes: evt.inputBytes,
          outputBytes: evt.outputBytes,
          queueDepth: evt.queueDepth,
          workerConcurrency: evt.workerConcurrency,
          executionContext: evt.executionContext,
          success: evt.success,
          outcome: null,
          errorCode: evt.errorCode,
          resolvedClientSupplierId: preflight.resolvedClientSupplierId,
          resolvedProfileName: preflight.resolvedProfileName,
          ...(evt.extras ? { extras: evt.extras } : {}),
        });
      },
    });

    try {
      for (const photo of photos) {
        const before = await queue.getCounts(sessionId);
        maxQueueDepth = Math.max(maxQueueDepth, before.pending);
        await queue.enqueueStablePhoto(sessionId, photo.id);
      }

      const drain = await queue.waitUntilExportable(sessionId, {
        producerBarrierCompleted: true,
        reason: 'EXPORT_PREFLIGHT',
        expectedFreezeId: freeze.freezeId,
        expectedFreezeGeneration: freeze.generation,
        timeoutMs,
        pollMs: 400,
      });

      if (!drain.exportable) {
        throw Object.assign(new Error(drain.structuralError ?? 'DRAIN_FAILED'), {
          code: drain.timedOut ? 'TIMEOUT' : drain.structuralError ?? 'DRAIN_FAILED',
        });
      }

      const strongStarted = monoNowMs();
      await queue.ensureJobsForEligiblePhotos(sessionId, {
        reason: 'EXPORT_PREFLIGHT',
      });
      // Real strong validation + digests happen inside exportSession → resolveExportPhotosFromStaging.
      sink.emit({
        sessionId,
        stage: 'export_preflight_ensure',
        monotonicStartMs: strongStarted,
        durationMs: monoNowMs() - strongStarted,
        executionContext: 'js',
        success: true,
        queueDepth: drain.queued + drain.processing,
        workerConcurrency: 1,
        extras: {
          strongValidationMode: 'EXPORT_PREFLIGHT',
          note: 'strong_validation_hash emitted during exportSession',
        },
      });

      const postLastInputStart = lastInjectMono;
      const exportStarted = monoNowMs();
      sink.emit({
        sessionId,
        stage: 'post_last_input',
        monotonicStartMs: postLastInputStart,
        durationMs: exportStarted - postLastInputStart,
        queueDepth: drain.queued + drain.processing,
        workerConcurrency: 1,
        executionContext: 'js',
        success: true,
        extras: {
          maxQueueDepth,
          configuredWorkers: 1,
          activeWorkers: 1,
        },
      });

      const exported = await this.deps.localCsvExport!.exportSession(sessionId, {
        onExportPhase: (phase) => {
          const exec =
            phase.extras && phase.extras.executionContext === 'native'
              ? 'native'
              : phase.extras && phase.extras.executionContext === 'js'
                ? 'js'
                : phase.phase === 'strong_validation_hash' || phase.phase === 'staging_hash'
                    ? 'native'
                    : 'unknown';
          sink.emit({
            sessionId,
            photoId: phase.photoId ?? null,
            sequence: phase.sequence ?? null,
            stage: phase.phase,
            monotonicStartMs: phase.monotonicStartMs,
            durationMs: phase.durationMs,
            executionContext: exec,
            success: phase.success,
            errorCode: phase.errorCode ?? null,
            inputBytes:
              typeof phase.extras?.inputBytes === 'number'
                ? phase.extras.inputBytes
                : typeof phase.extras?.bytesHashed === 'number'
                  ? phase.extras.bytesHashed
                  : null,
            outputBytes:
              typeof phase.extras?.outputBytes === 'number' ? phase.extras.outputBytes : null,
            ...(phase.extras ? { extras: phase.extras } : {}),
          });
        },
      });
      registry.exportIds.push(exported.exportId);

      const drafts = await this.deps.draftRepo.listForSession(sessionId);
      const draftByPhoto = canonicalizeDraftsByPhoto(drafts);
      const fixtureBySequence = new Map(
        command.fixtures.map((f) => [f.sequence, f] as const),
      );
      const dualRows: DualCorrectnessRow[] = [];
      let terminalCount = 0;
      for (const photo of photos) {
        const draft = draftByPhoto.get(photo.id) ?? null;
        const outcome = classifyDraftOutcome({
          draftStatus: draft?.status,
          errorCode: draft?.error_code,
          validationStatus: null,
          positionDetected: draft?.position_detected ?? null,
        });
        const admittedAt = admittedAtByPhotoId.get(photo.id) ?? exportStarted;
        const terminalAt = monoNowMs();
        sink.emit({
          sessionId,
          photoId: photo.id,
          sequence: photo.sequence_number,
          stage: 'photo_terminal',
          monotonicStartMs: admittedAt,
          durationMs: terminalAt - admittedAt,
          inputBytes: photo.size,
          outputBytes: null,
          queueDepth: 0,
          workerConcurrency: exportPrepMaxWorkers,
          executionContext: 'js',
          success: outcomeIsSuccess(outcome),
          outcome,
          errorCode: draft?.error_code ?? null,
          extras: {
            scannerProcessingMs: draft?.processing_ms ?? null,
            photoPipelineWallMs: terminalAt - admittedAt,
            photoQueueWaitMs: null,
            photoTerminalAtUtc: new Date().toISOString(),
            durationSemantics: 'admittedAt_to_terminalAt_wall',
          },
        });
        terminalCount += 1;

        // Dual correctness: exactly one row per photo (PIPELINE_ERROR if unrecoverable).
        const photoSeq = photo.sequence_number ?? 0;
        const fx =
          fixtureByAssetId.get(photo.asset_id) ??
          (photo.sequence_number != null
            ? fixtureBySequence.get(photo.sequence_number) ?? null
            : null);
        let dualRow: DualCorrectnessRow;
        try {
          const actual = reconstructActualFromDraft(draft);
          const rawDetected =
            this.deps.localCodeScan?.getRawDetectedPayloads(photo.id) ?? [];
          const scenarioKind = resolveFixtureScenarioKind(fx);
          dualRow = buildDualCorrectnessRow({
            benchmarkSequence: fx?.sequence ?? photoSeq,
            originalSequence: fx?.originalSequence ?? fx?.sequence ?? photoSeq,
            filename: fx?.filename ?? photo.display_name ?? photo.id,
            scenarioKind,
            labelsJson: fx?.labelsJson ?? null,
            actualRawDetectedPayloads: rawDetected,
            actualAcceptedPayloads: actual.actualAcceptedPayloads,
            actualRejectedPayloads: actual.actualRejectedPayloads,
            actualPosition: actual.actualPosition,
            actualItems: actual.actualItems,
            draftStatus: actual.draftStatus,
            errorCode: actual.errorCode,
            pipelineError: actual.pipelineError,
            scannerProcessingMs: draft?.processing_ms ?? null,
          });
        } catch (error) {
          const message = error instanceof Error ? error.message.slice(0, 160) : 'unknown';
          dualRow = buildDualCorrectnessRow({
            benchmarkSequence: fx?.sequence ?? photoSeq,
            originalSequence: fx?.originalSequence ?? fx?.sequence ?? photoSeq,
            filename: fx?.filename ?? photo.display_name ?? photo.id,
            scenarioKind: resolveFixtureScenarioKind(fx),
            labelsJson: fx?.labelsJson ?? null,
            actualRawDetectedPayloads: [],
            actualAcceptedPayloads: [],
            actualRejectedPayloads: [],
            actualPosition: null,
            actualItems: [],
            pipelineError: `PIPELINE_ERROR:${message}`,
            scannerProcessingMs: draft?.processing_ms ?? null,
          });
        }
        dualRows.push(dualRow);
        sink.emit({
          sessionId,
          photoId: photo.id,
          sequence: photo.sequence_number,
          stage: 'dual_correctness_row',
          monotonicStartMs: monoNowMs(),
          durationMs: 0,
          executionContext: 'js',
          success: dualRow.pipelineError == null,
          errorCode: dualRow.pipelineError,
          extras: {
            benchmarkSequence: dualRow.benchmarkSequence,
            originalSequence: dualRow.originalSequence,
            filename: dualRow.filename,
            scenarioKind: dualRow.scenarioKind,
            expectedValidPayloads: dualRow.expectedValidPayloads.join('|'),
            expectedFalsePayloads: dualRow.expectedFalsePayloads.join('|'),
            actualRawDetectedPayloads: dualRow.actualRawDetectedPayloads.join('|'),
            actualAcceptedPayloads: dualRow.actualAcceptedPayloads.join('|'),
            actualRejectedPayloads: dualRow.actualRejectedPayloads.join('|'),
            expectedPosition: dualRow.expectedPosition,
            actualPosition: dualRow.actualPosition,
            expectedItems: dualRow.expectedItems,
            actualItems: dualRow.actualItems,
            detectionResult: dualRow.detectionResult,
            domainResult: dualRow.domainResult,
            expectedDomainOutcome: dualRow.expectedDomainOutcome,
            pipelineError: dualRow.pipelineError,
            scannerProcessingMs: dualRow.scannerProcessingMs,
            detectionDetail: dualRow.detectionDetail ?? null,
            domainDetail: dualRow.domainDetail ?? null,
          },
        });
      }

      const dualSummary = summarizeDualCorrectness(dualRows);
      sink.emit({
        sessionId,
        stage: 'dual_correctness_summary',
        monotonicStartMs: monoNowMs(),
        durationMs: 0,
        executionContext: 'js',
        success: dualSummary.pipelineErrors === 0,
        extras: flattenDualSummaryExtras(dualSummary),
      });

      const counts = await queue.getCounts(sessionId);
      const pendingJobs = counts.queued + counts.processing + counts.failedRetryable;

      await measureStage(
        sink,
        { sessionId, stage: 'cleanup', executionContext: 'js' },
        async () => {
          await this.cleanup(registry);
          clearBenchmarkFixtures(runId);
        },
      );

      sink.emit({
        sessionId,
        stage: 'total_pipeline',
        monotonicStartMs: pipelineStart,
        durationMs: monoNowMs() - pipelineStart,
        inputBytes: command.fixtures.reduce((a, f) => a + f.sizeBytes, 0),
        queueDepth: pendingJobs,
        workerConcurrency: exportPrepMaxWorkers,
        executionContext: 'js',
        success: pendingJobs === 0 && terminalCount === command.fixtures.length,
        errorCode: pendingJobs === 0 ? null : 'PENDING_JOBS',
        extras: {
          coldWarm: command.coldWarm,
          maxQueueDepth,
          configuredWorkers: exportPrepMaxWorkers,
          exportPrepMaxWorkers,
          scannerConcurrency,
          ...summarizeHashCounters(sink.events),
        },
      });

      // Instrumentation gate for smoke acceptance (device-side soft check; Mac also validates).
      const photoEvents = sink.events.filter((e) => e.photoId);
      const missingFixture = photoEvents.some((e) => !e.fixtureId);
      const hasZipEntry = sink.events.some((e) => e.stage === 'zip_entry');
      const hasZipFinalize = sink.events.some((e) => e.stage === 'zip_finalize');
      const hasZipValidation = sink.events.some(
        (e) => e.stage === 'zip_validation' && e.durationMs > 0,
      );
      const positionOk = sink.events
        .filter((e) => e.stage === 'photo_terminal')
        .every((e) => {
          if (e.errorCode === 'POSITION_LABEL_DETECTED') {
            return e.outcome === 'position_detected' && e.success === true;
          }
          return true;
        });
      const hashCounters = summarizeHashCounters(sink.events);
      const stagingNative = sink.events.some(
        (e) =>
          e.stage === 'staging_hash' &&
          (e.extras?.hashMode === 'native_file' || e.extras?.hashImplementation === 'native_stream'),
      );
      // Integrity: strong validation always native-rehashes (no reused_persisted).
      const strongNative = sink.events.filter(
        (e) =>
          e.stage === 'strong_validation_hash' &&
          (e.extras?.hashMode === 'native_file' ||
            e.extras?.hashImplementation === 'native_stream'),
      ).length;
      const strongReusedUnexpected = sink.events.filter(
        (e) =>
          e.stage === 'strong_validation_hash' && e.extras?.hashMode === 'reused_persisted',
      ).length;
      const hashOk =
        hashCounters.base64FullFileHashCount === 0 &&
        stagingNative &&
        (command.fixtures.length < 3 ||
          (strongNative === command.fixtures.length && strongReusedUnexpected === 0));

      const draftLookups = sink.events.filter(
        (e) =>
          e.stage === 'draft_lookup' ||
          e.stage === 'draft_lookup_pre_scan' ||
          e.stage === 'draft_lookup_post_scan',
      );
      const draftLookupOk =
        command.fixtures.length < 3 ||
        (draftLookups.length >= command.fixtures.length &&
          draftLookups.every(
            (e) =>
              e.extras?.lookupMode === 'direct_indexed_lookup' &&
              Number(e.extras?.queryCount) === 1 &&
              Number(e.extras?.fullSessionRowsLoaded ?? 0) === 0,
          ) &&
          sink.events.some((e) => e.stage === 'draft_lookup_pre_scan') &&
          sink.events.some((e) => e.stage === 'draft_lookup_post_scan'));

      const stageOnceOk = (stage: string): boolean => {
        const rows = sink.events.filter((e) => e.stage === stage);
        return rows.length === 1 && Number(rows[0]!.durationMs) >= 0;
      };
      const hasStagingResolution = sink.events.some(
        (e) => e.stage === 'export_resolution_staging_validation',
      );
      let exportResolutionOk = true;
      if (hasStagingResolution || sink.events.some((e) => e.stage === 'export_resolution')) {
        exportResolutionOk =
          stageOnceOk('export_resolution') &&
          stageOnceOk('export_resolution_queries') &&
          stageOnceOk('export_resolution_freeze_checks') &&
          stageOnceOk('export_resolution_profile');
        if (hasStagingResolution) {
          const staging = sink.events.find(
            (e) => e.stage === 'export_resolution_staging_validation',
          );
          const hash = sink.events.find((e) => e.stage === 'export_resolution_hash_validation');
          const hashNestedOk =
            staging != null &&
            hash != null &&
            Number(hash.durationMs) <= Number(staging.durationMs) + 50;
          const entryOrOther =
            sink.events.some((e) => e.stage === 'export_resolution_entry_build') ||
            sink.events.some((e) => e.stage === 'export_resolution_other');
          const noFictitious =
            !sink.events.some(
              (e) =>
                (e.stage === 'export_resolution_ensure_jobs' || e.stage === 'export_resolution') &&
                Number(e.extras?.queryCount) === -1,
            );
          exportResolutionOk =
            exportResolutionOk &&
            stageOnceOk('export_resolution_ensure_jobs') &&
            stageOnceOk('export_resolution_staging_validation') &&
            stageOnceOk('export_resolution_hash_validation') &&
            stageOnceOk('export_resolution_scan_catchup') &&
            entryOrOther &&
            hashNestedOk &&
            noFictitious;
        }
      }

      const dualRowCountOk = dualRows.length === command.fixtures.length;

      const instrumentationInvalid =
        missingFixture ||
        !hasZipEntry ||
        !hasZipFinalize ||
        !hasZipValidation ||
        !positionOk ||
        !hashOk ||
        !draftLookupOk ||
        !exportResolutionOk ||
        !dualRowCountOk;

      const maxObservedScannerConcurrency =
        this.deps.localCodeScan?.getMaxObservedConcurrency() ?? 0;
      const nativeStats = await getNativeBarcodeScanConcurrencyStats();
      const maxObservedNativeScannerConcurrency = nativeStats.maxObserved;

      const envEnd = await finalizeBenchmarkEnvironment(envStart, {
        maxObservedScannerConcurrency,
        maxObservedNativeScannerConcurrency,
      });
      sink.emit({
        sessionId,
        stage: 'benchmark_environment_end',
        monotonicStartMs: monoNowMs(),
        durationMs: 0,
        executionContext: 'js',
        success: true,
        extras: {
          ...envEnd,
          exportPrepMaxWorkers,
          scannerConcurrency,
          maxObservedScannerConcurrency,
          maxObservedNativeScannerConcurrency,
          nativeStatsAvailable: nativeStats.available,
          ...flattenDualSummaryExtras(dualSummary),
        },
      });
      const envPath = `${this.deps.documentDirectory}${BENCHMARK_NAMESPACE_PREFIX}/${runId}/environment.json`;
      await FileSystem.writeAsStringAsync(envPath, JSON.stringify(envEnd, null, 2)).catch(
        () => undefined,
      );

      return {
        status:
          pendingJobs === 0 && !instrumentationInvalid
            ? 'COMPLETED'
            : 'FAILED',
        benchmarkRunId: runId,
        updatedAtUtc: new Date().toISOString(),
        terminalCount,
        expectedCount: command.fixtures.length,
        pendingJobs,
        errorCode:
          pendingJobs !== 0
            ? 'PENDING_JOBS'
            : instrumentationInvalid
              ? 'SMOKE_FAILED_INSTRUMENTATION_INVALID'
              : null,
        errorDetail: instrumentationInvalid
          ? `fixtureMissing=${missingFixture};zipEntry=${hasZipEntry};finalize=${hasZipFinalize};validation=${hasZipValidation};positionOk=${positionOk};hashOk=${hashOk};base64=${hashCounters.base64FullFileHashCount};strongNative=${strongNative};draftLookupOk=${draftLookupOk};exportResolutionOk=${exportResolutionOk};dualRowCountOk=${dualRowCountOk}`
          : null,
        profile: {
          resolvedClientId: preflight.resolvedClientId,
          resolvedSupplierId: preflight.resolvedSupplierId,
          resolvedClientSupplierId: preflight.resolvedClientSupplierId,
          resolvedProfileName: preflight.resolvedProfileName,
          itemProfileVersion: preflight.itemProfileVersion,
          positionProfileVersion: preflight.positionProfileVersion,
          configurationSource: preflight.configurationSource,
          snapshotResolved: preflight.snapshotResolved,
          hostInventoryId: preflight.hostInventoryId,
          fallbackUsed: preflight.fallbackUsed,
        },
        exportId: exported.exportId,
        sessionId,
        metricsPath: this.metricsPath(runId),
        extras: {
          exportPrepMaxWorkers,
          scannerConcurrency,
          maxObservedScannerConcurrency,
          maxObservedNativeScannerConcurrency,
          dualCorrectnessSummary: dualSummary,
          dualCorrectnessRows: dualRows,
        },
      };
    } finally {
      queue.setStageObserver(null);
    }
  }

  private async cleanup(registry: BenchmarkResourceRegistry): Promise<void> {
    const runId = registry.benchmarkRunId;
    if (registry.sessionId) {
      assertSessionOwnedByRun(registry.sessionId, runId);
      if (this.deps.sessionPurge) {
        await this.deps.sessionPurge.purgeSession(registry.sessionId).catch(() => undefined);
      }
      await this.deps.captureRepo
        .updateSessionStatus(registry.sessionId, 'cancelled')
        .catch(() => undefined);
    }
    // Deactivate bench aisle only (explicit id).
      if (registry.aisleId && registry.inventoryId) {
      await this.deps.catalogRepo
        .deactivateLocalAisle(registry.inventoryId, registry.aisleId)
        .catch(() => undefined);
    }
    const sandboxRoot = `${this.deps.documentDirectory}${BENCHMARK_NAMESPACE_PREFIX}/${runId}`;
    assertDeletableBenchmarkPath(sandboxRoot, runId);
    // Keep metrics/status; remove fixtures only.
    const fixturesDir = `${sandboxRoot}/fixtures`;
    assertDeletableBenchmarkPath(fixturesDir, runId);
    await FileSystem.deleteAsync(fixturesDir, { idempotent: true }).catch(() => undefined);
  }
}

/** Used by command watch to mint process id once per JS runtime. */
export function createBenchmarkProcessId(): string {
  return `proc-${createId()}`;
}

function resolveFixtureScenarioKind(
  fx: BenchmarkFixtureRef | null,
): import('./benchmarkFixtureOrder').BenchmarkManifestScenarioKind {
  if (fx?.scenarioKind) {
    const k = fx.scenarioKind.trim().toLowerCase();
    if (
      k === 'position' ||
      k === 'item' ||
      k === 'multi_true' ||
      k === 'multi_mixed' ||
      k === 'multi_false' ||
      k === 'other'
    ) {
      return k;
    }
  }
  const scenario = fx?.scenario ?? fx?.type ?? '';
  const category = fx?.category ?? fx?.type ?? '';
  return classifyScenarioKind(String(scenario), String(category));
}

function flattenDualSummaryExtras(
  summary: import('./benchmarkDualCorrectness').DualCorrectnessSummary,
): Record<string, number | string | boolean | null> {
  return {
    totalPhotos: summary.totalPhotos,
    detectionExact: summary.detectionExact,
    detectionPartial: summary.detectionPartial,
    detectionFalseNegative: summary.detectionFalseNegative,
    detectionUnexpectedExtra: summary.detectionUnexpectedExtra,
    detectionExactAccuracy: summary.detectionExactAccuracy,
    detectionRecall: summary.detectionRecall,
    domainExact: summary.domainExact,
    correctRejections: summary.correctRejections,
    falsePositives: summary.falsePositives,
    falseNegatives: summary.falseNegatives,
    wrongPosition: summary.wrongPosition,
    wrongItem: summary.wrongItem,
    wrongQuantity: summary.wrongQuantity,
    ambiguousExpected: summary.ambiguousExpected,
    ambiguousCorrect: summary.ambiguousCorrect,
    pipelineErrors: summary.pipelineErrors,
    domainExactAccuracy: summary.domainExactAccuracy,
    byScenarioJson: JSON.stringify(summary.byScenario),
  };
}

function summarizeHashCounters(
  events: readonly { stage: string; extras?: Readonly<Record<string, number | string | boolean | null>> }[],
): {
  nativeHashCount: number;
  reusedHashCount: number;
  validationFallbackHashCount: number;
  base64FullFileHashCount: number;
  totalBytesHashed: number;
  hashesPerPhoto: number;
} {
  let nativeHashCount = 0;
  let reusedHashCount = 0;
  let validationFallbackHashCount = 0;
  let base64FullFileHashCount = 0;
  let totalBytesHashed = 0;
  let photoHashEvents = 0;
  for (const e of events) {
    if (e.stage !== 'staging_hash' && e.stage !== 'strong_validation_hash') continue;
    photoHashEvents += 1;
    const mode = String(e.extras?.hashMode ?? '');
    const impl = String(e.extras?.hashImplementation ?? '');
    const source = String(e.extras?.hashSource ?? '');
    const bytes =
      typeof e.extras?.bytesHashed === 'number'
        ? e.extras.bytesHashed
        : typeof e.extras?.hashInputBytes === 'number'
          ? e.extras.hashInputBytes
          : 0;
    if (mode === 'js_base64_full_file' || impl === 'js_base64_full_file') {
      base64FullFileHashCount += 1;
    }
    if (mode === 'reused_persisted') {
      reusedHashCount += 1;
    } else if (mode === 'native_file' || impl === 'native_stream') {
      nativeHashCount += 1;
      totalBytesHashed += bytes;
      if (source === 'validation_fallback') {
        validationFallbackHashCount += 1;
      }
    }
  }
  const terminals = events.filter((e) => e.stage === 'photo_terminal').length;
  return {
    nativeHashCount,
    reusedHashCount,
    validationFallbackHashCount,
    base64FullFileHashCount,
    totalBytesHashed,
    hashesPerPhoto: terminals > 0 ? (nativeHashCount + reusedHashCount) / terminals : photoHashEvents,
  };
}
