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

import { sha256BytesHex } from '../../core/payloadFingerprint';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import type { ExportPrepRepository } from '../../database/repositories/exportPrepRepository';
import type { LocalCsvExportRepository } from '../../database/repositories/localCsvExportRepository';
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
import { exportPhotoFileName } from '../exportPrep/exportPhotoFileName';
import { stagingFileExists } from '../exportPrep/exportStaging';
import { writeStoreZipAtomic } from '../exportPrep/streamingZipWriter';
import type { ExportPrepJobRow } from '../exportPrep/exportPrepTypes';
import {
  listCanonicalExportPhotos,
  selectExportPackagingPhotos,
} from '../exportPrep/eligibleExportPhotos';
import { buildLocalCsvExport } from './buildLocalCsvExport';
import { isDraftExportReady } from './supplierExportSemantics';
import { diagnoseExportBlockers } from './localCsvExportPreflight';
import { sha256Hex } from './csvFormat';
import { base64ToUint8Array } from './binaryCodec';
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
}

export class LocalCsvExportService {
  private zipProgressListener: ((done: number, total: number) => void) | null = null;

  constructor(private readonly deps: LocalCsvExportServiceDeps) {}

  /** UI-facing ZIP progress hook (stable abstraction; share cancel does not clear staging). */
  setZipProgressListener(listener: ((done: number, total: number) => void) | null): void {
    this.zipProgressListener = listener;
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

  async exportSession(sessionId: string): Promise<ExportedLocalCsv> {
    if (this.deps.enabled === false) {
      throw new Error('La exportación CSV local no está habilitada.');
    }
    const session = await this.deps.captureRepo.getSession(sessionId);
    if (!session) {
      throw new Error('No se encontró la captura local.');
    }
    const { photos } = await listCanonicalExportPhotos(this.deps.captureRepo, sessionId, session);
    const eligible = selectExportPackagingPhotos(photos);
    let drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);

    const prepEnabled = this.deps.exportPrepEnabled === true && this.deps.exportPrepRepo != null;
    let scanMode: ExportScanMode = prepEnabled ? 'catch_up' : 'legacy';
    let prepByPhoto = new Map<string, ExportPrepJobRow>();

    if (prepEnabled) {
      if (this.deps.ensureExportPrepJobs) {
        await this.deps.ensureExportPrepJobs(sessionId);
      }
      const prepRepo = this.deps.exportPrepRepo!;
      const jobs = await prepRepo.listForSession(sessionId);
      prepByPhoto = new Map(jobs.map((j) => [j.capture_photo_id, j]));

      for (const photo of eligible) {
        const job = prepByPhoto.get(photo.id);
        if (!job) {
          throw new Error(
            `PACKAGE_EXPORT_PREP_INCOMPLETE: falta preparación de exportación para ${photo.id}`,
          );
        }
        if (job.status === 'FAILED_TERMINAL') {
          throw new Error(
            `PACKAGE_EXPORT_PREP_TERMINAL: ${photo.id} (${job.error_code ?? 'FAILED_TERMINAL'}). Reintentá o excluí la foto.`,
          );
        }
        if (job.status === 'FAILED_RETRYABLE') {
          throw new Error(
            `PACKAGE_EXPORT_PREP_FAILED: ${photo.id} (${job.error_code ?? job.status})`,
          );
        }
        if (job.status !== 'READY') {
          throw new Error(
            `PACKAGE_EXPORT_PREP_PENDING: ${photo.id} aún en ${job.status}`,
          );
        }
      }

      const allReady = eligible.every((p) => prepByPhoto.get(p.id)?.status === 'READY');
      if (allReady) {
        scanMode = 'skipped_all_ready';
        this.deps.logger?.info('recovery', {
          where: 'local_export_scan_skipped',
          code: 'EXPORT_SCAN_SKIPPED_ALL_READY',
          sessionId,
          photo_count: eligible.length,
        });
      } else {
        await this.ensureLocalCodeScans(session, eligible, drafts);
        drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => drafts);
      }
    } else {
      await this.ensureLocalCodeScans(session, eligible, drafts);
      drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => drafts);
    }

    const confirmed = await this.deps.confirmedRepo.listForSession(sessionId).catch(() => []);

    const resolved = await this.deps.profileResolver
      ?.resolveForAisle(session.inventory_id, session.aisle_id)
      .catch(() => null);
    const blocker = diagnoseExportBlockers(
      eligible,
      drafts,
      resolved
        ? {
            clientSupplierId:
              resolved.item.clientSupplierId ?? resolved.position.clientSupplierId ?? null,
            itemSource: resolved.item.source,
            positionSource: resolved.position.source,
          }
        : null,
    );
    if (blocker) {
      throw new Error(`${blocker.code}: ${blocker.detail}`);
    }

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

    const packagedPhotos = prepEnabled
      ? await readEligiblePhotosFromStaging(eligible, prepByPhoto, this.deps.exportPrepRepo!)
      : await readEligiblePhotosStrictLegacy(eligible);

    const estimatedBytes = packagedPhotos.reduce((sum, p) => sum + (p.size_bytes || 0), 0);
    const maxBytes = this.deps.maxExportUncompressedBytes ?? 480 * 1024 * 1024;
    if (estimatedBytes > maxBytes) {
      throw new Error(
        `PACKAGE_EXPORT_TOO_LARGE: estimado ${estimatedBytes} bytes supera el límite ${maxBytes}`,
      );
    }

    const photoFingerprintPart = packagedPhotos
      .map((p) => `${p.capture_photo_id}:${p.sha256}`)
      .join(',');
    const contentFingerprint = await sha256Hex(
      [
        `pkg-v${LOCAL_PACKAGE_VERSION}`,
        session.active_freeze_id ?? '',
        built.checksumSha256,
        photoFingerprintPart,
      ].join('|'),
    );

    const existing = await this.deps.exportRepo.findByFingerprint(contentFingerprint);
    if (existing?.file_uri) {
      const csvInfo = await FileSystem.getInfoAsync(existing.file_uri);
      const zipCandidate = existing.file_uri.replace(/\.csv$/i, '.zip');
      const zipInfo = await FileSystem.getInfoAsync(zipCandidate);
      const zipOk =
        zipInfo.exists &&
        'size' in zipInfo &&
        typeof zipInfo.size === 'number' &&
        zipInfo.size > 0;
      if (csvInfo.exists && zipOk) {
        return {
          exportId: existing.export_id,
          fileUri: existing.file_uri,
          zipUri: zipCandidate,
          checksumSha256: existing.checksum_sha256,
          rowCount: existing.row_count,
          photoCount: packagedPhotos.length,
          packageChecksumSha256: contentFingerprint,
          reused: true,
          scanMode,
        };
      }
    }

    const dir = `${FileSystem.documentDirectory ?? FileSystem.cacheDirectory}aisle-exports/`;
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
    const csvUri = `${dir}${built.exportId}.csv`;
    const zipUri = `${dir}${built.exportId}.zip`;
    const tmpCsv = `${dir}${built.exportId}.tmp.csv`;
    const publishToken = `${Date.now()}`;
    const tmpZip = `${dir}${built.exportId}.${publishToken}.tmp.zip`;

    const photoEntries = packagedPhotos.map(({ getBytes: _g, ...meta }) => meta);
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
      freeze_id: session.active_freeze_id,
      freeze_generation: session.capture_freeze_generation,
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

    const manifestBytes = utf8Encode(`${JSON.stringify(manifest, null, 2)}\n`);
    const csvBytes = utf8Encode(built.csv);

    try {
      await FileSystem.writeAsStringAsync(tmpCsv, built.csv, {
        encoding: FileSystem.EncodingType.UTF8,
      });
      await writeStoreZipAtomic({
        targetUri: tmpZip,
        onProgress: (done, total) => {
          this.deps.onZipProgress?.(done, total);
          this.zipProgressListener?.(done, total);
        },
        entries: [
          { path: 'results.csv', getBytes: () => csvBytes },
          { path: 'manifest.json', getBytes: () => manifestBytes },
          ...packagedPhotos.map((photo) => ({
            path: `photos/${photo.file_name}`,
            getBytes: photo.getBytes,
          })),
        ],
      });
      // Publish both only after ZIP succeeded.
      await FileSystem.deleteAsync(csvUri, { idempotent: true }).catch(() => undefined);
      await FileSystem.deleteAsync(zipUri, { idempotent: true }).catch(() => undefined);
      await FileSystem.moveAsync({ from: tmpCsv, to: csvUri });
      await FileSystem.moveAsync({ from: tmpZip, to: zipUri });
    } catch (error) {
      await FileSystem.deleteAsync(tmpCsv, { idempotent: true }).catch(() => undefined);
      await FileSystem.deleteAsync(tmpZip, { idempotent: true }).catch(() => undefined);
      throw error;
    }

    const now = new Date().toISOString();
    await this.deps.exportRepo.insert({
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
      freeze_id: built.freezeId,
      exported_at: built.exportedAt,
      shared_at: null,
      created_at: now,
      updated_at: now,
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
    };
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

async function readEligiblePhotosFromStaging(
  eligible: CapturePhotoRow[],
  prepByPhoto: Map<string, ExportPrepJobRow>,
  prepRepo: ExportPrepRepository,
): Promise<PackagedPhotoMeta[]> {
  const out: PackagedPhotoMeta[] = [];
  for (let i = 0; i < eligible.length; i += 1) {
    const photo = eligible[i]!;
    const job = prepByPhoto.get(photo.id);
    if (!job || job.status !== 'READY') {
      throw new Error(`PACKAGE_EXPORT_PREP_NOT_READY: ${photo.id}`);
    }
    if (!(await stagingFileExists(job.staging_uri))) {
      await prepRepo.invalidateReady(
        photo.id,
        'EXPORT_PREP_STAGING_MISSING',
        'Staging ausente al exportar',
      );
      throw new Error(
        `PACKAGE_STAGING_MISSING: no se encontró el archivo preparado de ${photo.id}`,
      );
    }
    const stagingUri = job.staging_uri!;
    const fileName = job.export_file_name || exportPhotoFileName(
      photo.id,
      photo.sequence_number ?? i + 1,
      photo.display_name,
    );
    const expectedSha = job.sha256;
    const expectedSize = job.size_bytes;

    out.push({
      capture_photo_id: photo.id,
      client_file_id: photo.client_file_id ?? photo.id,
      sequence_number: photo.sequence_number ?? i + 1,
      file_name: fileName,
      mime_type: photo.mime_type || 'image/jpeg',
      size_bytes: expectedSize ?? 0,
      sha256: expectedSha ?? '',
      width: photo.width ?? 0,
      height: photo.height ?? 0,
      asset_variant: 'ORIGINAL',
      getBytes: async () => {
        const b64 = await FileSystem.readAsStringAsync(stagingUri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        const bytes = base64ToUint8Array(b64);
        if (bytes.byteLength === 0) {
          throw new Error(`PACKAGE_PHOTO_READ_FAILED: foto vacía ${photo.id}`);
        }
        if (expectedSize != null && bytes.byteLength !== expectedSize) {
          await prepRepo.invalidateReady(
            photo.id,
            'EXPORT_PREP_SIZE_MISMATCH',
            `size ${bytes.byteLength} != ${expectedSize}`,
          );
          throw new Error(`PACKAGE_STAGING_CHECKSUM: tamaño no coincide para ${photo.id}`);
        }
        const sha = sha256BytesHex(bytes);
        if (expectedSha && sha !== expectedSha) {
          await prepRepo.invalidateReady(
            photo.id,
            'EXPORT_PREP_SHA_MISMATCH',
            'sha256 mismatch',
          );
          throw new Error(`PACKAGE_STAGING_CHECKSUM: sha256 no coincide para ${photo.id}`);
        }
        return bytes;
      },
    });
  }
  return out;
}

/** Legacy path: read originals from MediaStore URI (flag off). */
async function readEligiblePhotosStrictLegacy(
  eligible: CapturePhotoRow[],
): Promise<PackagedPhotoMeta[]> {
  const out: PackagedPhotoMeta[] = [];
  for (let i = 0; i < eligible.length; i += 1) {
    const photo = eligible[i]!;
    const seq = photo.sequence_number ?? i + 1;
    const name = exportPhotoFileName(photo.id, seq, photo.display_name);
    const sourceUri = photo.uri;
    let cached: Uint8Array | null = null;
    const load = async (): Promise<Uint8Array> => {
      if (cached) return cached;
      try {
        const b64 = await FileSystem.readAsStringAsync(sourceUri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        cached = base64ToUint8Array(b64);
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        throw new Error(
          `PACKAGE_PHOTO_READ_FAILED: no se pudo leer la foto ${photo.id} (${name}): ${detail}`,
        );
      }
      if (cached.byteLength === 0) {
        throw new Error(`PACKAGE_PHOTO_READ_FAILED: foto vacía ${photo.id} (${name})`);
      }
      return cached;
    };
    const bytes = await load();
    out.push({
      capture_photo_id: photo.id,
      client_file_id: photo.client_file_id ?? photo.id,
      sequence_number: seq,
      file_name: name,
      mime_type: photo.mime_type || 'image/jpeg',
      size_bytes: bytes.byteLength,
      sha256: sha256BytesHex(bytes),
      width: photo.width ?? 0,
      height: photo.height ?? 0,
      asset_variant: 'ORIGINAL',
      getBytes: load,
    });
  }
  return out;
}
