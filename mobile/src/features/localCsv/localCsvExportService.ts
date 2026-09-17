/**
 * Local aisle export: CSV results + ZIP (CSV + freeze photos) for offline handoff.
 * Share uses expo-sharing so the file is attached (RN Share.message is text-only on Android).
 *
 * Package contract (package_version 2):
 * - results.csv + manifest.json + photos/*
 * - Every manifest photo entry must exist in the ZIP with matching sha256
 * - Unreadable photos abort the export (strict / COMPLETE packages only)
 */

import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import type { ExportPrepRepository } from '../../database/repositories/exportPrepRepository';
import {
  resolveZipUri,
  type LocalCsvExportRepository,
} from '../../database/repositories/localCsvExportRepository';
import {
  ExportAttemptTransitionError,
  type LocalExportAttemptRepository,
} from '../../database/repositories/localExportAttemptRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import type { LocalLabelProfileResolver } from '../offlineRecognition/localLabelProfileResolver';
import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { Logger } from '../../core/logging';
import {
  normalizePreparationProcessingMode,
  resolveLocalScanProcessingMode,
} from '../../core/imagePreparationPolicy';
import { createId } from '../../shared/createId';
import {
  hashPreparedFileSha256,
  hashPreparedMetaSha256,
} from '../localCodeScan/preparedAssetHash';
import type { LocalCodeScanStrategy } from '../localCodeScan/localCodeScanStrategy';
import { writeStoreZipAtomic } from '../exportPrep/streamingZipWriter';
import { ZipWriteError } from '../exportPrep/boundedZipWriter';
import { validateOnDiskStoreZip } from '../exportPrep/boundedOnDiskZipValidator';
import { assertZipWritePlatformSupported } from '../exportPrep/zipWritePlatform';
import { getNodeProcess } from '../exportPrep/nodeRuntime';
import {
  assertModernZipPhotosArePrepEligible,
  listCanonicalExportPhotos,
  selectExpectedZipPhotos,
} from '../exportPrep/eligibleExportPhotos';
import { ExportFromStagingError } from '../exportPrep/exportFromStagingErrors';
import {
  resolveExportPhotosFromOriginals,
  resolveExportPhotosFromStaging,
  type ResolvedExportPhoto,
} from '../exportPrep/exportPhotoResolver';
import { decideExportSourcePolicy } from '../exportPrep/exportSourcePolicy';
import type { OriginalFallbackReason } from '../exportPrep/exportSourcePolicy';
import { buildPackageContentFingerprint } from '../exportPrep/packageFingerprint';
import { validateExistingExportPackage } from '../exportPrep/existingPackageValidator';
import { rethrowExportOrZip } from '../exportPrep/mapZipWriteError';
import {
  assessStorageSpace,
  type StorageFailure,
} from '../exportPrep/artifactRetentionPolicy';
import {
  buildExportPublishPaths,
  ensureAisleExportsDir,
} from '../exportPrep/exportArtifactPaths';
import { getFreeDiskBytesHint } from '../exportPrep/exportStaging';
import { buildLocalCsvExport } from './buildLocalCsvExport';
import { isDraftExportReady } from './supplierExportSemantics';
import { diagnoseExportBlockers } from './localCsvExportPreflight';
import { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from './localPackageContract';

export { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from './localPackageContract';

/** Set when export path skips catch-up CODE_SCAN because all eligible photos are READY. */
export type ExportScanMode = 'catch_up' | 'skipped_all_ready' | 'legacy';

function utf8Encode(text: string): Uint8Array {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(text);
  }
  const out: number[] = [];
  for (let i = 0; i < text.length; i += 1) {
    const c = text.charCodeAt(i);
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    else out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
  }
  return Uint8Array.from(out);
}

export interface LocalCsvExportServiceDeps {
  readonly captureRepo: CaptureRepository;
  readonly draftRepo: LocalDetectionDraftRepository;
  readonly confirmedRepo: ConfirmedLocalResultRepository;
  readonly exportRepo: LocalCsvExportRepository;
  readonly deviceId: string;
  readonly companyId?: string | null;
  readonly clientId?: string | null;
  readonly enabled?: boolean;
  /** When set, ZIP export runs local CODE_SCAN before building rows (offline path). */
  readonly localCodeScan?: LocalCodeScanStrategy | null;
  readonly localCodeScanEnabled?: boolean;
  readonly logger?: Logger | null;
  readonly profileResolver?: LocalLabelProfileResolver | null;
  /** When set + flag path, export reads READY staging only (no MediaStore fallback). */
  readonly exportPrepRepo?: ExportPrepRepository | null;
  readonly exportPrepEnabled?: boolean;
  /** Backfill missing jobs before export preflight (historical sessions). */
  readonly ensureExportPrepJobs?: ((sessionId: string) => Promise<void>) | null;
  /** Soft limit for sum of staged bytes before ZIP build. */
  readonly maxExportUncompressedBytes?: number;
  readonly onZipProgress?: (done: number, total: number) => void;
  /** Phase 6 durable export attempt catalog. */
  readonly attemptRepo?: LocalExportAttemptRepository | null;
}

export interface ExportSessionOptions {
  readonly signal?: AbortSignal;
  readonly onProgress?: (progress: import('../exportPrep/boundedZipWriter').ZipWriteProgress) => void;
  /**
   * Optional timing observer (benchmark / diagnostics). No-op when unset —
   * does not alter export behavior.
   */
  readonly onExportPhase?: (event: LocalExportPhaseEvent) => void;
}

export type LocalExportPhaseName =
  | 'export_resolution'
  | 'strong_validation'
  | 'strong_validation_hash'
  | 'csv_build'
  | 'csv_write'
  | 'manifest_build'
  | 'zip_open'
  | 'zip_entry'
  | 'zip_finalize'
  | 'zip_digest'
  | 'zip_validation'
  | 'total_export';

export interface LocalExportPhaseEvent {
  readonly phase: LocalExportPhaseName;
  readonly monotonicStartMs: number;
  readonly durationMs: number;
  readonly success: boolean;
  readonly errorCode?: string | null;
  readonly photoId?: string | null;
  readonly sequence?: number | null;
  readonly extras?: Readonly<Record<string, number | string | boolean | null>>;
}

export interface ExportedLocalCsv {
  readonly exportId: string;
  readonly fileUri: string;
  readonly zipUri: string | null;
  readonly checksumSha256: string;
  readonly rowCount: number;
  readonly photoCount: number;
  readonly packageChecksumSha256: string | null;
  readonly reused: boolean;
  /** Observability: whether catch-up CODE_SCAN ran. */
  readonly scanMode?: ExportScanMode;
  /** Phase 4: photos read from validated staging. */
  readonly stagingPhotoCount?: number;
  /** Phase 4: photos read via controlled original fallback. */
  readonly originalFallbackCount?: number;
  readonly fallbackReason?: OriginalFallbackReason | null;
}

interface PackagedPhotoMeta {
  readonly capture_photo_id: string;
  readonly client_file_id: string;
  readonly sequence_number: number;
  readonly file_name: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly sha256: string;
  readonly width: number;
  readonly height: number;
  readonly asset_variant: 'ORIGINAL' | 'PREPARED';
  readonly getBytes: () => Promise<Uint8Array>;
  /** Staging/original absolute path for stream-append ZIP write (no JS Base64). */
  readonly sourceAbsolutePath?: string;
}

function toPackagedMeta(photo: ResolvedExportPhoto): PackagedPhotoMeta {
  return {
    capture_photo_id: photo.capturePhotoId,
    client_file_id: photo.clientFileId,
    sequence_number: photo.sequenceNumber,
    file_name: photo.exportFileName,
    mime_type: photo.mimeType,
    size_bytes: photo.sizeBytes,
    sha256: photo.sha256,
    width: photo.width,
    height: photo.height,
    asset_variant: photo.source === 'VALIDATED_STAGING' ? 'PREPARED' : 'ORIGINAL',
    getBytes: photo.getBytes,
    ...(photo.uri ? { sourceAbsolutePath: photo.uri } : {}),
  };
}

export class LocalCsvExportService {
  private zipProgressListener:
    | ((done: number, total: number, stage?: string) => void)
    | null = null;
  /** Serialize exports per session (double-tap / concurrent callers). */
  private readonly sessionExportLocks = new Map<string, Promise<unknown>>();
  /** Active export operations — service-owned cancel, not UI-only AbortController. */
  private readonly activeExports = new Map<
    string,
    { readonly controller: AbortController; readonly promise: Promise<unknown> }
  >();

  constructor(private readonly deps: LocalCsvExportServiceDeps) {}

  /** UI-facing ZIP progress hook (stable abstraction; share cancel does not clear staging). */
  setZipProgressListener(
    listener: ((done: number, total: number, stage?: string) => void) | null,
  ): void {
    this.zipProgressListener = listener;
  }

  /**
   * Abort in-flight export for session and wait until the promise settles.
   * Used by SessionArtifactPurgeCoordinator — UI may also call this.
   */
  async cancelActiveExport(sessionId: string): Promise<void> {
    const active = this.activeExports.get(sessionId);
    if (!active) return;
    active.controller.abort();
    try {
      await active.promise;
    } catch {
      // expected after abort
    }
  }

  isExportActive(sessionId: string): boolean {
    return this.activeExports.has(sessionId);
  }

  /**
   * Offline ZIP path no longer goes through upload-prepare, so CODE_SCAN must run here
   * (or on photo-stable) before asserting export readiness.
   */
  private async ensureLocalCodeScans(
    session: CaptureSessionRow,
    photos: readonly CapturePhotoRow[],
    existingDrafts: readonly LocalDetectionDraftRow[],
  ): Promise<void> {
    const strategy = this.deps.localCodeScan;
    if (!strategy || this.deps.localCodeScanEnabled !== true) {
      return;
    }
    const draftByPhoto = new Map(existingDrafts.map((d) => [d.capture_photo_id, d]));
    const sessionMode = normalizePreparationProcessingMode(session.preparation_processing_mode);
    const processingMode = resolveLocalScanProcessingMode(sessionMode, true);
    // Export uses persisted local recognition; always OFFLINE resolver semantics.
    const recognitionContext: 'ONLINE' | 'OFFLINE' = 'OFFLINE';

    for (const photo of photos) {
      if (photo.status === 'excluded' || photo.status === 'rejected' || photo.status === 'undecodable') {
        continue;
      }
      const existing = draftByPhoto.get(photo.id);
      if (isDraftExportReady(existing)) {
        continue;
      }
      const preparedUri = photo.local_transform_uri || photo.uri;
      let fingerprint: string;
      try {
        fingerprint = await hashPreparedFileSha256(preparedUri);
      } catch {
        fingerprint = hashPreparedMetaSha256({
          uri: preparedUri,
          bytes: photo.upload_size ?? photo.size ?? 0,
          width: photo.width ?? 0,
          height: photo.height ?? 0,
        });
      }
      try {
        await strategy.execute({
          capturePhotoId: photo.id,
          captureSessionId: session.id,
          clientFileId: photo.client_file_id,
          preparedUri,
          preparedAssetFingerprint: fingerprint,
          processingMode,
          flagEnabled: true,
          cancelRequested: photo.upload_cancel_requested === 1,
          inventoryId: session.inventory_id,
          aisleId: session.aisle_id,
          recognitionContext,
        });
      } catch (error) {
        this.deps.logger?.warn('local_export_scan_failed', {
          code: 'LOCAL_EXPORT_SCAN_FAILED',
          capture_photo_id: photo.id,
          error_code:
            error && typeof error === 'object' && 'code' in error
              ? String((error as { code: unknown }).code)
              : undefined,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  async exportSession(
    sessionId: string,
    options?: ExportSessionOptions,
  ): Promise<ExportedLocalCsv> {
    const previous = this.sessionExportLocks.get(sessionId) ?? Promise.resolve();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const chained = previous.catch(() => undefined).then(() => gate);
    this.sessionExportLocks.set(sessionId, chained);
    await previous.catch(() => undefined);

    const controller = new AbortController();
    const external = options?.signal;
    const onExternalAbort = () => controller.abort();
    if (external) {
      if (external.aborted) controller.abort();
      else external.addEventListener('abort', onExternalAbort, { once: true });
    }

    const work = this.exportSessionUnlocked(sessionId, {
      ...options,
      signal: controller.signal,
    });
    this.activeExports.set(sessionId, { controller, promise: work });

    try {
      return await work;
    } finally {
      if (external) external.removeEventListener('abort', onExternalAbort);
      this.activeExports.delete(sessionId);
      release();
      if (this.sessionExportLocks.get(sessionId) === chained) {
        this.sessionExportLocks.delete(sessionId);
      }
    }
  }

  private async exportSessionUnlocked(
    sessionId: string,
    options?: ExportSessionOptions,
  ): Promise<ExportedLocalCsv> {
    assertZipWritePlatformSupported();
    if (this.deps.enabled === false) {
      throw new Error('La exportación CSV local no está habilitada.');
    }
    const mono = () => {
      const p = (globalThis as { performance?: { now(): number } }).performance;
      return typeof p?.now === 'function' ? p.now() : Date.now();
    };
    const emitPhase = (
      phase: LocalExportPhaseName,
      started: number,
      extra?: {
        readonly success?: boolean;
        readonly errorCode?: string | null;
        readonly photoId?: string | null;
        readonly sequence?: number | null;
        readonly extras?: Readonly<Record<string, number | string | boolean | null>>;
      },
    ) => {
      if (!options?.onExportPhase) return;
      try {
        options.onExportPhase({
          phase,
          monotonicStartMs: started,
          durationMs: mono() - started,
          success: extra?.success !== false,
          errorCode: extra?.errorCode ?? null,
          photoId: extra?.photoId ?? null,
          sequence: extra?.sequence ?? null,
          ...(extra?.extras ? { extras: extra.extras } : {}),
        });
      } catch {
        // never break export for observer errors
      }
    };

    const totalExportStarted = mono();
    const preflightStarted = Date.now();
    const resolutionStarted = mono();
    const session = await this.deps.captureRepo.getSession(sessionId);
    if (!session) {
      throw new ExportFromStagingError('SESSION_MISSING', 'No se encontró la captura local.');
    }
    const freezeIdAtStart = session.active_freeze_id;
    const freezeGenerationAtStart = session.capture_freeze_generation ?? null;

    const { photos } = await listCanonicalExportPhotos(this.deps.captureRepo, sessionId, session);
    const eligible = selectExpectedZipPhotos(photos);
    let drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);

    const prepFlagOn = this.deps.exportPrepEnabled === true && this.deps.exportPrepRepo != null;
    const sourcePolicy = decideExportSourcePolicy({
      exportPrepEnabled: prepFlagOn,
      session,
    });
    let scanMode: ExportScanMode =
      sourcePolicy.mode === 'staging_required' ? 'catch_up' : 'legacy';
    let stagingPhotoCount = 0;
    let originalFallbackCount = 0;
    let fallbackReason: OriginalFallbackReason | null = sourcePolicy.fallbackReason;
    let packagedResolved: readonly ResolvedExportPhoto[] = [];

    if (sourcePolicy.mode === 'staging_required') {
      assertModernZipPhotosArePrepEligible(eligible);
      if (this.deps.ensureExportPrepJobs) {
        await this.deps.ensureExportPrepJobs(sessionId);
      }
      const prepRepo = this.deps.exportPrepRepo!;
      const jobs = await prepRepo.listForSession(sessionId);
      const prepByPhoto = new Map(jobs.map((j) => [j.capture_photo_id, j]));

      const strongStarted = mono();
      let reusedHashCount = 0;
      let validationFallbackHashCount = 0;
      let nativeHashCount = 0;
      let totalBytesHashed = 0;
      const resolved = await resolveExportPhotosFromStaging({
        session,
        expectedPhotos: eligible,
        jobsByPhotoId: prepByPhoto,
        prepRepo,
        onReadyValidation: ({ photoId, sequence, result }) => {
          const dig = result.digest;
          const hashMode = dig?.hashMode ?? 'native_file';
          const hashSource = dig?.hashSource ?? 'validation_fallback';
          const bytesHashed = dig?.bytesHashed ?? 0;
          const digestDuration = dig?.durationMs ?? 0;
          if (hashMode === 'reused_persisted') {
            reusedHashCount += 1;
          } else {
            nativeHashCount += 1;
            validationFallbackHashCount += 1;
            totalBytesHashed += bytesHashed;
          }
          if (options?.onExportPhase) {
            try {
              options.onExportPhase({
                phase: 'strong_validation_hash',
                monotonicStartMs: mono() - digestDuration,
                durationMs: digestDuration,
                success: result.ok,
                errorCode: result.ok ? null : (result.failure ?? 'STAGING_SHA_MISMATCH'),
                photoId,
                sequence,
                extras: {
                  hashMode,
                  hashSource,
                  bytesHashed,
                  hashCount: hashMode === 'reused_persisted' ? 0 : 1,
                  fullFileReadCount: hashMode === 'reused_persisted' ? 0 : 1,
                  hashImplementation:
                    hashMode === 'reused_persisted' ? 'cached_digest' : 'native_stream',
                  digestReused: hashMode === 'reused_persisted',
                  reuseReason: dig?.reason ?? null,
                  base64FullFileHashCount: 0,
                },
              });
            } catch {
              // never break export for observer errors
            }
          }
        },
      });
      emitPhase('strong_validation', strongStarted, {
        extras: {
          photoCount: eligible.length,
          reusedHashCount,
          validationFallbackHashCount,
          nativeHashCount,
          base64FullFileHashCount: 0,
          totalBytesHashed,
          hashesPerPhoto:
            eligible.length > 0
              ? (nativeHashCount + reusedHashCount) / eligible.length
              : 0,
        },
      });
      packagedResolved = resolved.photos;
      stagingPhotoCount = resolved.stagingCount;
      originalFallbackCount = resolved.originalFallbackCount;
      fallbackReason = resolved.fallbackReason;

      if (resolved.allStagingStrongValidated) {
        scanMode = 'skipped_all_ready';
        this.deps.logger?.info('recovery', {
          where: 'local_export_scan_skipped',
          code: 'EXPORT_SCAN_SKIPPED_ALL_READY',
          sessionId,
          photo_count: eligible.length,
          staging_photo_count: stagingPhotoCount,
          preflight_ms: Date.now() - preflightStarted,
        });
      } else {
        await this.ensureLocalCodeScans(session, eligible, drafts);
        drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => drafts);
      }
    } else {
      this.deps.logger?.info('recovery', {
        where: 'local_export_original_fallback',
        code: 'EXPORT_ORIGINAL_FALLBACK',
        sessionId,
        reason: sourcePolicy.fallbackReason,
        photo_count: eligible.length,
      });
      await this.ensureLocalCodeScans(session, eligible, drafts);
      drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => drafts);
      const resolved = await resolveExportPhotosFromOriginals({
        session,
        expectedPhotos: eligible,
        fallbackReason: sourcePolicy.fallbackReason ?? 'FEATURE_DISABLED',
      });
      packagedResolved = resolved.photos;
      stagingPhotoCount = resolved.stagingCount;
      originalFallbackCount = resolved.originalFallbackCount;
      fallbackReason = resolved.fallbackReason;
    }

    const confirmed = await this.deps.confirmedRepo.listForSession(sessionId).catch(() => []);

    const resolvedProfiles = await this.deps.profileResolver
      ?.resolveForAisle(session.inventory_id, session.aisle_id)
      .catch(() => null);
    const blocker = diagnoseExportBlockers(
      eligible,
      drafts,
      resolvedProfiles
        ? {
            clientSupplierId:
              resolvedProfiles.item.clientSupplierId ??
              resolvedProfiles.position.clientSupplierId ??
              null,
            itemSource: resolvedProfiles.item.source,
            positionSource: resolvedProfiles.position.source,
          }
        : null,
    );
    if (blocker) {
      throw new Error(`${blocker.code}: ${blocker.detail}`);
    }
    emitPhase('export_resolution', resolutionStarted, {
      extras: {
        eligibleCount: eligible.length,
        draftCount: drafts.length,
        stagingPhotoCount,
      },
    });

    const csvBuildStarted = mono();
    const built = await buildLocalCsvExport({
      session,
      photos: eligible,
      drafts,
      confirmed,
      deviceId: this.deps.deviceId,
      companyId: this.deps.companyId ?? null,
      clientId: this.deps.clientId ?? null,
      freezeId: session.active_freeze_id,
      freezeGeneration: session.capture_freeze_generation,
    });
    emitPhase('csv_build', csvBuildStarted, {
      extras: {
        rowCount: built.rowCount,
        photoCount: eligible.length,
        csvBytes: utf8Encode(built.csv).byteLength,
      },
    });

    const packagedPhotos = packagedResolved.map((photo) => {
      const meta = toPackagedMeta(photo);
      if (sourcePolicy.mode !== 'staging_required') {
        return meta;
      }
      // Recheck freeze identity while reading/streaming bytes (long exports).
      return {
        ...meta,
        getBytes: async () => {
          await this.assertFreezeUnchanged(
            sessionId,
            freezeIdAtStart,
            freezeGenerationAtStart,
            'getBytes',
          );
          return meta.getBytes();
        },
      };
    });
    if (packagedPhotos.length !== eligible.length) {
      throw new ExportFromStagingError(
        'PHOTO_SET_MISMATCH',
        `packaged ${packagedPhotos.length} != expected ${eligible.length}`,
      );
    }

    const estimatedBytes = packagedPhotos.reduce((sum, p) => sum + (p.size_bytes || 0), 0);
    const maxBytes = this.deps.maxExportUncompressedBytes ?? 480 * 1024 * 1024;
    if (estimatedBytes > maxBytes) {
      throw new ExportFromStagingError(
        'EXPORT_TOO_LARGE',
        `estimado ${estimatedBytes} bytes supera el límite ${maxBytes}`,
      );
    }

    const freeBytes = await getFreeDiskBytesHint();
    const space = assessStorageSpace({
      freeBytes,
      estimatedPayloadBytes: estimatedBytes,
    });
    if (space.level === 'INSUFFICIENT_FOR_OPERATION') {
      this.deps.logger?.warn('storage.insufficient_for_export', {
        sessionRef: sessionId.slice(0, 8),
        freeBytes: space.freeBytes,
        requiredBytes: space.requiredBytes,
      });
      throw new ExportFromStagingError(
        'STORAGE_INSUFFICIENT_FOR_EXPORT',
        `libre=${space.freeBytes} requerido≈${space.requiredBytes}`,
      );
    }
    if (space.level === 'LOW_SPACE_WARNING') {
      this.deps.logger?.warn('storage.low_space', {
        sessionRef: sessionId.slice(0, 8),
        freeBytes: space.freeBytes,
        requiredBytes: space.requiredBytes,
        failure: 'STORAGE_LOW' satisfies StorageFailure,
      });
    }

    const contentFingerprint = await buildPackageContentFingerprint({
      freezeId: freezeIdAtStart,
      freezeGeneration: freezeGenerationAtStart,
      csvChecksumSha256: built.checksumSha256,
      photos: packagedPhotos.map((p) => ({
        capturePhotoId: p.capture_photo_id,
        sequenceNumber: p.sequence_number,
        fileName: p.file_name,
        mimeType: p.mime_type,
        sizeBytes: p.size_bytes,
        sha256: p.sha256,
        assetVariant: p.asset_variant,
      })),
    });

    const existing =
      (await this.deps.exportRepo.findBySessionAndFingerprint(sessionId, contentFingerprint)) ??
      (await this.deps.exportRepo.findByFingerprint(contentFingerprint));
    if (existing?.file_uri) {
      const zipCandidate = existing.file_uri.replace(/\.csv$/i, '.zip');
      const validated = await validateExistingExportPackage({
        row: existing,
        expectedContentFingerprint: contentFingerprint,
        zipUri: zipCandidate,
      });
      if (validated.ok) {
        this.deps.logger?.info('recovery', {
          where: 'local_export_reused',
          code: 'EXPORT_PACKAGE_REUSED',
          sessionId,
          export_id: existing.export_id,
          staging_photo_count: stagingPhotoCount,
          original_fallback_count: originalFallbackCount,
        });
        return {
          exportId: existing.export_id,
          fileUri: existing.file_uri,
          zipUri: validated.zipUri,
          checksumSha256: existing.checksum_sha256,
          rowCount: existing.row_count,
          photoCount: packagedPhotos.length,
          packageChecksumSha256: contentFingerprint,
          reused: true,
          scanMode,
          stagingPhotoCount,
          originalFallbackCount,
          fallbackReason,
        };
      }
      this.deps.logger?.warn('recovery', {
        where: 'local_export_reuse_rejected',
        code: 'EXPORT_PACKAGE_REUSE_REJECTED',
        sessionId,
        export_id: existing.export_id,
        reason: validated.reason,
      });
      // Fall through to rebuild; do not delete the prior row/files of another fingerprint.
    }

    await this.assertFreezeUnchanged(
      sessionId,
      freezeIdAtStart,
      freezeGenerationAtStart,
      'pre_build',
      sourcePolicy.mode === 'staging_required',
    );

    await ensureAisleExportsDir();
    const publishToken = `${Date.now()}`;
    const paths = buildExportPublishPaths({
      exportId: built.exportId,
      publishToken,
    });
    const { csvUri, zipUri, tmpCsv, tmpZip } = paths;

    const attemptId = createId();
    const attemptNow = new Date().toISOString();
    if (this.deps.attemptRepo) {
      await this.deps.attemptRepo.insert({
        id: attemptId,
        capture_session_id: sessionId,
        freeze_id: freezeIdAtStart,
        freeze_generation: freezeGenerationAtStart,
        content_fingerprint: contentFingerprint,
        state: 'CREATED',
        tmp_csv_uri: tmpCsv,
        tmp_zip_uri: tmpZip,
        final_csv_uri: null,
        final_zip_uri: null,
        started_at: attemptNow,
        heartbeat_at: attemptNow,
        completed_at: null,
        error_code: null,
        created_at: attemptNow,
        updated_at: attemptNow,
      });
    }

    const photoEntries = packagedPhotos.map(
      ({ getBytes: _g, sourceAbsolutePath: _path, ...meta }) => meta,
    );
    const packageChecksumSha256 = contentFingerprint;
    const manifest = {
      schema_version: built.schemaVersion,
      package_kind: LOCAL_PACKAGE_KIND,
      package_version: LOCAL_PACKAGE_VERSION,
      status: 'COMPLETE',
      export_id: built.exportId,
      exported_at: built.exportedAt,
      inventory_id: session.inventory_id,
      aisle_id: session.aisle_id,
      capture_session_id: sessionId,
      freeze_id: freezeIdAtStart,
      freeze_generation: freezeGenerationAtStart,
      row_count: built.rowCount,
      expected_photo_count: eligible.length,
      included_photo_count: packagedPhotos.length,
      missing_photos: [] as const,
      csv_checksum_sha256: built.checksumSha256,
      checksum_sha256: built.checksumSha256,
      checksum_algorithm: built.checksumAlgorithm,
      package_checksum_sha256: packageChecksumSha256,
      summary: {
        photo_count: packagedPhotos.length,
        position_event_count: built.positionEventCount,
        product_result_count: built.productResultCount,
        rejected_detection_count: built.rejectedDetectionCount,
      },
      photos: photoEntries,
    };

    if (manifest.expected_photo_count !== manifest.included_photo_count) {
      throw new ExportFromStagingError(
        'PACKAGE_VALIDATION_FAILED',
        `expected_photo_count ${manifest.expected_photo_count} != included ${manifest.included_photo_count}`,
      );
    }

    const manifestBuildStarted = mono();
    const manifestBytes = utf8Encode(`${JSON.stringify(manifest, null, 2)}\n`);
    const csvBytes = utf8Encode(built.csv);
    emitPhase('manifest_build', manifestBuildStarted, {
      extras: {
        manifestBytes: manifestBytes.byteLength,
        csvBytes: csvBytes.byteLength,
        expectedPhotoCount: manifest.expected_photo_count,
      },
    });
    const zipBuildStarted = Date.now();

    let csvPublished = false;
    let zipPublished = false;
    let zipSizeBytes = 0;
    let zipSha256 = '';
    try {
      if (this.deps.attemptRepo) {
        await this.deps.attemptRepo.transitionState(attemptId, 'WRITING');
      }
      const csvWriteStarted = mono();
      await FileSystem.writeAsStringAsync(tmpCsv, built.csv, {
        encoding: FileSystem.EncodingType.UTF8,
      });
      emitPhase('csv_write', csvWriteStarted, {
        extras: {
          csvBytes: csvBytes.byteLength,
          writeTarget: 'tmp_csv_sidecar',
        },
      });

      const zipOpenStarted = mono();
      emitPhase('zip_open', zipOpenStarted, { extras: { entryCount: 2 + packagedPhotos.length } });

      let lastCompletedEntries = 0;
      let entryWallStart = mono();
      let finalizeWallStart: number | null = null;
      let digestWallStart: number | null = null;
      const photoByZipPath = new Map<string, (typeof packagedPhotos)[number]>(
        packagedPhotos.map((p) => [`photos/${p.file_name}`, p]),
      );

      const written = await writeStoreZipAtomic({
        targetUri: tmpZip,
        maxTotalBytes: maxBytes,
        ...(options?.signal ? { signal: options.signal } : {}),
        onProgress: (done, total) => {
          this.deps.onZipProgress?.(done, total);
          this.zipProgressListener?.(done, total, 'WRITING_ENTRIES');
        },
        onZipProgress: (p) => {
          options?.onProgress?.(p);
          const stageLabel =
            p.stage === 'PREPARING'
              ? 'Preparando'
              : p.stage === 'WRITING_ENTRIES'
                ? 'Escribiendo fotos'
                : p.stage === 'WRITING_DIRECTORY'
                  ? 'Cerrando ZIP'
                  : p.stage === 'VALIDATING'
                    ? 'Validando'
                    : 'Publicando';
          this.zipProgressListener?.(
            p.stage === 'WRITING_ENTRIES'
              ? Math.min(p.completedEntries, Math.max(0, p.totalEntries - 1))
              : p.completedEntries,
            Math.max(1, p.totalEntries),
            stageLabel,
          );
          if (p.stage === 'WRITING_ENTRIES' && p.completedEntries > lastCompletedEntries) {
            const entryPath = p.currentEntry ?? '';
            const entryKind = entryPath.startsWith('photos/')
              ? 'photo'
              : entryPath.endsWith('.csv')
                ? 'csv'
                : entryPath.endsWith('.json')
                  ? 'manifest'
                  : 'other';
            const photoMeta = photoByZipPath.get(entryPath);
            const ext = entryPath.includes('.') ? entryPath.slice(entryPath.lastIndexOf('.')) : '';
            const sized =
              entryKind === 'csv'
                ? csvBytes.byteLength
                : entryKind === 'manifest'
                  ? manifestBytes.byteLength
                  : (photoMeta?.size_bytes ?? null);
            emitPhase('zip_entry', entryWallStart, {
              photoId: photoMeta?.capture_photo_id ?? null,
              sequence: photoMeta?.sequence_number ?? null,
              extras: {
                entryKind,
                entryIndex: p.completedEntries,
                entryExt: ext,
                inputBytes: sized,
                outputBytes: sized,
                executionContext:
                  entryKind === 'photo'
                    ? photoMeta?.sourceAbsolutePath
                      ? 'native'
                      : 'js'
                    : 'js',
              },
            });
            lastCompletedEntries = p.completedEntries;
            entryWallStart = mono();
          }
          // Central directory + EOCD (before sink.close / incremental digest).
          if (p.stage === 'WRITING_DIRECTORY' && finalizeWallStart == null) {
            finalizeWallStart = mono();
          }
          // Writer emits VALIDATING immediately before sink.close()+digestHex().
          if (p.stage === 'VALIDATING' && digestWallStart == null) {
            digestWallStart = mono();
          }
          if (p.stage !== 'WRITING_ENTRIES' || p.completedEntries === 0) {
            return;
          }
          if (p.completedEntries % 10 !== 0 && p.completedEntries !== p.totalEntries) {
            return;
          }
          this.deps.logger?.info('recovery', {
            where: 'local_export_zip_progress',
            code: 'ZIP_WRITE_PROGRESS',
            sessionId,
            stage: p.stage,
            completed_entries: p.completedEntries,
            total_entries: p.totalEntries,
            processed_bytes: p.processedBytes,
            total_bytes: p.totalBytes,
          });
        },
        entries: [
          {
            path: 'results.csv',
            sizeBytes: csvBytes.byteLength,
            getBytes: () => csvBytes,
          },
          {
            path: 'manifest.json',
            sizeBytes: manifestBytes.byteLength,
            getBytes: () => manifestBytes,
          },
          ...packagedPhotos.map((photo) => ({
            path: `photos/${photo.file_name}`,
            sizeBytes: photo.size_bytes,
            expectedSha256: photo.sha256,
            // Stream from staging/original path — avoids Base64 read+write through JS.
            ...(photo.sourceAbsolutePath
              ? {
                  sourceAbsolutePath: photo.sourceAbsolutePath,
                  beforeAppend: async () => {
                    await this.assertFreezeUnchanged(
                      sessionId,
                      freezeIdAtStart,
                      freezeGenerationAtStart,
                      'zip_append_photo',
                      sourcePolicy.mode === 'staging_required',
                    );
                  },
                }
              : { getBytes: photo.getBytes }),
          })),
        ],
      });
      const writeReturnedAt = mono();
      const finalizeStarted = finalizeWallStart ?? writeReturnedAt;
      // Finalize = CD/EOCD wall only (ends when VALIDATING / close begins).
      const finalizeEnd = digestWallStart ?? writeReturnedAt;
      if (options?.onExportPhase) {
        try {
          options.onExportPhase({
            phase: 'zip_finalize',
            monotonicStartMs: finalizeStarted,
            durationMs: Math.max(0, finalizeEnd - finalizeStarted),
            success: true,
            errorCode: null,
            photoId: null,
            sequence: null,
            extras: {
              entryCount: written.entryCount,
              peakOpenEntries: written.peakOpenEntries,
            },
          });
        } catch {
          // never break export for observer errors
        }
      }
      // Digest = sink.close + digestHex (incremental_write; not a second full-file read here).
      const digestStarted = digestWallStart ?? writeReturnedAt;
      emitPhase('zip_digest', digestStarted, {
        extras: {
          digestMode: 'incremental_write',
          fullFileRead: false,
          zipBytes: written.byteLength,
        },
      });
      zipSizeBytes = written.byteLength;
      zipSha256 = written.sha256;
      if (zipSizeBytes <= 0 || !zipSha256 || written.peakOpenEntries > 1) {
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          written.peakOpenEntries > 1
            ? `ZIP concurrency invariant peakOpen=${written.peakOpenEntries}`
            : 'ZIP tmp inválido tras build',
        );
      }

      this.zipProgressListener?.(written.entryCount, written.entryCount, 'Validando');
      if (this.deps.attemptRepo) {
        await this.deps.attemptRepo.transitionState(attemptId, 'VALIDATING');
      }
      const roots: string[] = [];
      if (FileSystem.documentDirectory) roots.push(FileSystem.documentDirectory);
      if (FileSystem.cacheDirectory) roots.push(FileSystem.cacheDirectory);
      const tmpdir = getNodeProcess()?.env?.TMPDIR;
      if (tmpdir) {
        roots.push(tmpdir);
      }
      roots.push('/tmp');
      const onDiskStarted = mono();
      const onDisk = await validateOnDiskStoreZip({
        // After writeStoreZipAtomic, bytes live at tmpZip (not the nested .tmp.<ts> sink path).
        uri: tmpZip,
        allowedRoots: roots,
        expectedSizeBytes: zipSizeBytes,
        expectedSha256: zipSha256,
        expectedContentFingerprint: contentFingerprint,
        computeSha256: true,
        verifyCrcAll: false,
      });
      emitPhase('zip_validation', onDiskStarted, {
        success: onDisk.ok,
        errorCode: onDisk.ok ? null : onDisk.reason,
        extras: {
          expectedSize: zipSizeBytes,
          actualSize: onDisk.ok ? onDisk.zipSizeBytes : null,
          rangesRead: onDisk.ok ? onDisk.rangeReads : null,
          bytesRead: onDisk.ok ? onDisk.maxBufferBytes : null,
          digestRecomputed: true,
          validationMode: 'on_disk_store_zip',
          fullFileRead: true,
        },
      });
      if (!onDisk.ok) {
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          `ZIP tmp validation: ${onDisk.reason}`,
        );
      }
      if (
        typeof written.entryCount === 'number' &&
        onDisk.entryCount !== written.entryCount
      ) {
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          `ZIP entry count ${onDisk.entryCount} != written ${written.entryCount}`,
        );
      }

      this.deps.logger?.info('recovery', {
        where: 'local_export_zip_completed',
        code: 'ZIP_WRITE_COMPLETED',
        sessionId,
        entry_count: written.entryCount,
        zip_size_bytes: zipSizeBytes,
        method: written.method,
        peak_open_entries: written.peakOpenEntries,
        range_reads: onDisk.rangeReads,
        max_buffer_bytes: onDisk.maxBufferBytes,
        duration_ms: Date.now() - zipBuildStarted,
      });

      await this.assertFreezeUnchanged(
        sessionId,
        freezeIdAtStart,
        freezeGenerationAtStart,
        'post_zip',
        sourcePolicy.mode === 'staging_required',
      );

      this.zipProgressListener?.(written.entryCount, written.entryCount, 'Publicando');
      if (this.deps.attemptRepo) {
        await this.deps.attemptRepo.transitionState(attemptId, 'PUBLISHING', {
          final_csv_uri: csvUri,
          final_zip_uri: zipUri,
        });
      }
      await this.assertFreezeUnchanged(
        sessionId,
        freezeIdAtStart,
        freezeGenerationAtStart,
        'pre_publish',
        sourcePolicy.mode === 'staging_required',
      );

      if (options?.signal?.aborted) {
        throw Object.assign(new Error('ZIP_CANCELLED'), {
          name: 'ZipWriteError',
          code: 'ZIP_CANCELLED',
        });
      }
      await FileSystem.moveAsync({ from: tmpCsv, to: csvUri });
      csvPublished = true;
      if (options?.signal?.aborted) {
        // CSV moved — keep for recoverable publish; do not delete as success.
        throw Object.assign(new Error('ZIP_CANCELLED'), {
          name: 'ZipWriteError',
          code: 'ZIP_CANCELLED',
        });
      }
      await FileSystem.moveAsync({ from: tmpZip, to: zipUri });
      zipPublished = true;
      const csvInfo = await FileSystem.getInfoAsync(csvUri);
      const zipInfo = await FileSystem.getInfoAsync(zipUri);
      const zipOk =
        zipInfo.exists &&
        'size' in zipInfo &&
        typeof zipInfo.size === 'number' &&
        zipInfo.size > 0;
      if (!csvInfo.exists || !zipOk) {
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          'CSV/ZIP no válidos tras move',
        );
      }
      if (typeof zipInfo.size === 'number' && zipInfo.size > 0) {
        zipSizeBytes = zipInfo.size;
      }
    } catch (error) {
      const cancelled =
        (error instanceof Error &&
          error.name === 'ZipWriteError' &&
          'code' in error &&
          (error as ZipWriteError).code === 'ZIP_CANCELLED') ||
        options?.signal?.aborted === true ||
        error instanceof ExportAttemptTransitionError;

      // After both finals exist on disk, do not delete them — leave PUBLISHING/FAILED
      // with URIs for bootstrap recovery / purge. Only scrub temps / partial single file.
      const bothFinalsOnDisk = csvPublished && zipPublished;
      if (!bothFinalsOnDisk) {
        await FileSystem.deleteAsync(tmpCsv, { idempotent: true }).catch(() => undefined);
        await FileSystem.deleteAsync(tmpZip, { idempotent: true }).catch(() => undefined);
        if (csvPublished && !zipPublished) {
          await FileSystem.deleteAsync(csvUri, { idempotent: true }).catch(() => undefined);
        }
      } else {
        await FileSystem.deleteAsync(tmpCsv, { idempotent: true }).catch(() => undefined);
        await FileSystem.deleteAsync(tmpZip, { idempotent: true }).catch(() => undefined);
      }

      if (this.deps.attemptRepo) {
        try {
          if (bothFinalsOnDisk && !cancelled) {
            // Stay recoverable: keep PUBLISHING with final URIs (bootstrap completes insert).
            await this.deps.attemptRepo.heartbeat(attemptId, new Date().toISOString());
          } else {
            await this.deps.attemptRepo.transitionState(
              attemptId,
              cancelled ? 'CANCELLED' : 'FAILED',
              {
                completed_at: new Date().toISOString(),
                error_code: cancelled
                  ? 'ZIP_CANCELLED'
                  : error instanceof ExportFromStagingError
                    ? error.code
                    : error instanceof ExportAttemptTransitionError
                      ? 'TRANSITION_REJECTED'
                      : 'EXPORT_FAILED',
                ...(csvPublished ? { final_csv_uri: csvUri } : {}),
                ...(zipPublished ? { final_zip_uri: zipUri } : {}),
              },
            );
          }
        } catch (transitionError) {
          this.deps.logger?.warn('recovery', {
            where: 'local_export_attempt_terminal_failed',
            sessionId,
            message:
              transitionError instanceof Error
                ? transitionError.message
                : String(transitionError),
          });
          throw transitionError instanceof ExportAttemptTransitionError
            ? transitionError
            : error;
        }
      }
      if (cancelled) {
        this.deps.logger?.info('recovery', {
          where: 'local_export_zip_cancelled',
          code: 'ZIP_CANCELLED',
          sessionId,
        });
      } else if (
        error instanceof Error &&
        error.name === 'ZipWriteError' &&
        'code' in error &&
        (error as ZipWriteError).code === 'ZIP_SOURCE_CHANGED'
      ) {
        this.deps.logger?.warn('recovery', {
          where: 'local_export_zip_source_changed',
          code: 'ZIP_SOURCE_CHANGED',
          sessionId,
        });
      }
      rethrowExportOrZip(error);
    }

    await this.assertFreezeUnchanged(
      sessionId,
      freezeIdAtStart,
      freezeGenerationAtStart,
      'pre_insert',
      sourcePolicy.mode === 'staging_required',
    );

    const now = new Date().toISOString();
    const row = {
      id: createId(),
      export_id: built.exportId,
      schema_version: built.schemaVersion,
      scope: built.scope,
      capture_session_id: sessionId,
      inventory_id: session.inventory_id,
      aisle_id: session.aisle_id,
      row_count: built.rowCount,
      checksum_sha256: built.checksumSha256,
      checksum_algorithm: built.checksumAlgorithm,
      content_fingerprint: contentFingerprint,
      file_uri: csvUri,
      zip_uri: zipUri,
      freeze_id: freezeIdAtStart,
      zip_size_bytes: zipSizeBytes,
      zip_sha256: zipSha256,
      package_checksum_sha256: packageChecksumSha256,
      exported_at: built.exportedAt,
      shared_at: null,
      created_at: now,
      updated_at: now,
    };
    const inserted = await this.deps.exportRepo.tryInsert(row);
    if (!inserted) {
      // Peer won the race — prefer their durable row; discard this attempt's files only.
      await FileSystem.deleteAsync(csvUri, { idempotent: true }).catch(() => undefined);
      await FileSystem.deleteAsync(zipUri, { idempotent: true }).catch(() => undefined);
      if (this.deps.attemptRepo) {
        await this.deps.attemptRepo.transitionState(attemptId, 'CANCELLED', {
          completed_at: new Date().toISOString(),
          error_code: 'PEER_WON_RACE',
        });
      }
      const peer =
        (await this.deps.exportRepo.findBySessionAndFingerprint(sessionId, contentFingerprint)) ??
        (await this.deps.exportRepo.findByFingerprint(contentFingerprint));
      if (peer?.file_uri) {
        const peerZip = resolveZipUri(peer) ?? peer.file_uri.replace(/\.csv$/i, '.zip');
        const validated = await validateExistingExportPackage({
          row: peer,
          expectedContentFingerprint: contentFingerprint,
          zipUri: peerZip,
        });
        if (validated.ok) {
          return {
            exportId: peer.export_id,
            fileUri: peer.file_uri,
            zipUri: validated.zipUri,
            checksumSha256: peer.checksum_sha256,
            rowCount: peer.row_count,
            photoCount: packagedPhotos.length,
            packageChecksumSha256: contentFingerprint,
            reused: true,
            scanMode,
            stagingPhotoCount,
            originalFallbackCount,
            fallbackReason,
          };
        }
      }
      throw new ExportFromStagingError(
        'PACKAGE_VALIDATION_FAILED',
        'Conflicto de exportación concurrente sin paquete válido peer',
      );
    }

    if (this.deps.attemptRepo) {
      await this.deps.attemptRepo.transitionState(attemptId, 'COMPLETE', {
        final_csv_uri: csvUri,
        final_zip_uri: zipUri,
        completed_at: now,
        content_fingerprint: contentFingerprint,
      });
    }

    this.deps.logger?.info('recovery', {
      where: 'local_export_complete',
      code: 'EXPORT_PACKAGE_BUILT',
      sessionId,
      export_id: built.exportId,
      staging_photo_count: stagingPhotoCount,
      original_fallback_count: originalFallbackCount,
      fallback_reason: fallbackReason,
      scan_mode: scanMode,
      preflight_ms: Date.now() - preflightStarted,
      zip_build_ms: Date.now() - zipBuildStarted,
      uncompressed_bytes: estimatedBytes,
    });

    // Definitive 100% only after durable persist.
    this.zipProgressListener?.(1, 1, 'Listo');

    emitPhase('total_export', totalExportStarted, {
      extras: {
        rowCount: built.rowCount,
        photoCount: packagedPhotos.length,
        zipBytes: zipSizeBytes,
      },
    });

    return {
      exportId: built.exportId,
      fileUri: csvUri,
      zipUri,
      checksumSha256: built.checksumSha256,
      rowCount: built.rowCount,
      photoCount: packagedPhotos.length,
      packageChecksumSha256,
      reused: false,
      scanMode,
      stagingPhotoCount,
      originalFallbackCount,
      fallbackReason,
    };
  }

  private async assertFreezeUnchanged(
    sessionId: string,
    expectedFreezeId: string | null,
    expectedFreezeGeneration: number | null,
    stage: string,
    enforce = true,
  ): Promise<void> {
    if (!enforce) return;
    const sessionNow = await this.deps.captureRepo.getSession(sessionId);
    if (!sessionNow) {
      throw new ExportFromStagingError('SESSION_MISSING', 'La sesión desapareció durante la exportación.');
    }
    if (
      sessionNow.active_freeze_id !== expectedFreezeId ||
      (sessionNow.capture_freeze_generation ?? null) !== expectedFreezeGeneration
    ) {
      this.deps.logger?.warn('error', {
        code: 'EXPORT_FREEZE_CHANGED',
        sessionId,
        stage,
        expected_freeze_id: expectedFreezeId,
        actual_freeze_id: sessionNow.active_freeze_id,
      });
      throw new ExportFromStagingError(
        'FREEZE_CHANGED',
        `El freeze cambió durante la exportación (${stage}); no se publicó el ZIP.`,
      );
    }
  }

  /** Run local CODE_SCAN on session photos before aisle/session export (no CSV/ZIP). */
  async prepareSessionForExport(sessionId: string): Promise<void> {
    const session = await this.deps.captureRepo.getSession(sessionId);
    if (!session) {
      return;
    }
    let photos = await this.deps.captureRepo.listPhotos(sessionId);
    if (session.active_freeze_id) {
      photos = await this.deps.captureRepo.listFreezePhotos(session.active_freeze_id);
    }
    const eligible = photos.filter((p) => p.status !== 'excluded' && p.status !== 'rejected');
    const drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);
    await this.ensureLocalCodeScans(session, eligible, drafts);
  }

  /**
   * Share the ZIP (preferred) or CSV as a real file attachment.
   * Do not use RN Share.message — Android email clients receive only the text body.
   */
  async shareExport(fileUri: string, exportId: string, preferredZipUri?: string | null): Promise<void> {
    const target = preferredZipUri && (await FileSystem.getInfoAsync(preferredZipUri)).exists
      ? preferredZipUri
      : fileUri;
    const available = await Sharing.isAvailableAsync();
    if (!available) {
      throw new Error('Este dispositivo no permite compartir archivos.');
    }
    const isZip = /\.zip$/i.test(target);
    await Sharing.shareAsync(target, {
      mimeType: isZip ? 'application/zip' : 'text/csv',
      dialogTitle: isZip ? 'Exportar pasillo (ZIP + CSV)' : 'Exportar resultados CSV',
      UTI: isZip ? 'public.zip-archive' : 'public.comma-separated-values-text',
    });
    await this.deps.exportRepo.markShared(exportId, new Date().toISOString());
  }
}
