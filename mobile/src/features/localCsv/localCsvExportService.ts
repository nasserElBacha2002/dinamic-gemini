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
import { zipSync } from 'fflate';

import { sha256BytesHex } from '../../core/payloadFingerprint';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import type { LocalCsvExportRepository } from '../../database/repositories/localCsvExportRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
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
import { buildLocalCsvExport } from './buildLocalCsvExport';
import { isDraftExportReady } from './supplierExportSemantics';
import { sha256Hex } from './csvFormat';
import { base64ToUint8Array, uint8ArrayToBase64 } from './binaryCodec';
import { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from './localPackageContract';

export { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from './localPackageContract';

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
}

interface PackagedPhoto {
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
  readonly bytes: Uint8Array;
}

export class LocalCsvExportService {
  constructor(private readonly deps: LocalCsvExportServiceDeps) {}

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
      if (photo.status !== 'stable') {
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
    let photos = await this.deps.captureRepo.listPhotos(sessionId);
    if (session.active_freeze_id) {
      photos = await this.deps.captureRepo.listFreezePhotos(session.active_freeze_id);
    }
    const eligible = photos.filter((p) => p.status !== 'excluded' && p.status !== 'rejected');
    let drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);
    await this.ensureLocalCodeScans(session, eligible, drafts);
    drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => drafts);
    const confirmed = await this.deps.confirmedRepo.listForSession(sessionId).catch(() => []);

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

    const packagedPhotos = await readEligiblePhotosStrict(eligible);
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
        };
      }
    }

    const dir = `${FileSystem.documentDirectory ?? FileSystem.cacheDirectory}aisle-exports/`;
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
    const csvUri = `${dir}${built.exportId}.csv`;
    const zipUri = `${dir}${built.exportId}.zip`;
    const tmpCsv = `${dir}${built.exportId}.tmp.csv`;
    const tmpZip = `${dir}${built.exportId}.tmp.zip`;

    await FileSystem.writeAsStringAsync(tmpCsv, built.csv, {
      encoding: FileSystem.EncodingType.UTF8,
    });
    await FileSystem.moveAsync({ from: tmpCsv, to: csvUri });

    const photoEntries = packagedPhotos.map(
      ({ bytes: _bytes, ...meta }) => meta,
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

    const zipEntries: Record<string, Uint8Array> = {
      'results.csv': utf8Encode(built.csv),
      'manifest.json': utf8Encode(`${JSON.stringify(manifest, null, 2)}\n`),
    };
    for (const photo of packagedPhotos) {
      zipEntries[`photos/${photo.file_name}`] = photo.bytes;
    }

    const zipped = zipSync(zipEntries, { level: 0 });
    // Drop entry buffers before base64 encode to reduce peak overlap.
    for (const key of Object.keys(zipEntries)) {
      delete zipEntries[key];
    }
    const zipB64 = uint8ArrayToBase64(zipped);
    await FileSystem.writeAsStringAsync(tmpZip, zipB64, {
      encoding: FileSystem.EncodingType.Base64,
    });
    await FileSystem.deleteAsync(zipUri, { idempotent: true }).catch(() => undefined);
    await FileSystem.moveAsync({ from: tmpZip, to: zipUri });

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
    let drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);
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

async function readEligiblePhotosStrict(eligible: CapturePhotoRow[]): Promise<PackagedPhoto[]> {
  const out: PackagedPhoto[] = [];
  for (let i = 0; i < eligible.length; i += 1) {
    const photo = eligible[i]!;
    const seq = photo.sequence_number ?? i + 1;
    const name = photoFileName(photo.id, seq, photo.display_name);
    // Prefer original capture bytes for OCR / evidence; prepared is upload-optimized.
    const sourceUri = photo.uri;
    const assetVariant: 'ORIGINAL' | 'PREPARED' = 'ORIGINAL';
    let bytes: Uint8Array;
    try {
      const b64 = await FileSystem.readAsStringAsync(sourceUri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      bytes = base64ToUint8Array(b64);
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(
        `PACKAGE_PHOTO_READ_FAILED: no se pudo leer la foto ${photo.id} (${name}): ${detail}`,
      );
    }
    if (bytes.byteLength === 0) {
      throw new Error(`PACKAGE_PHOTO_READ_FAILED: foto vacía ${photo.id} (${name})`);
    }
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
      asset_variant: assetVariant,
      bytes,
    });
  }
  return out;
}

function photoFileName(photoId: string, sequence: number, displayName: string | null): string {
  const safeId = photoId.replace(/[^a-zA-Z0-9_-]/g, '_');
  const ext = (displayName && /\.[a-z0-9]+$/i.exec(displayName)?.[0]) || '.jpg';
  return `${String(sequence).padStart(4, '0')}_${safeId}${ext}`;
}
