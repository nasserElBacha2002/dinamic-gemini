/**
 * Resolve each ZIP photo from validated staging (primary) or controlled original fallback.
 */

import * as FileSystem from 'expo-file-system';

import { sha256BytesHex } from '../../core/payloadFingerprint';
import type { ExportPrepRepository } from '../../database/repositories/exportPrepRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { base64ToUint8Array } from '../localCsv/binaryCodec';
import { exportPhotoFileName } from './exportPhotoFileName';
import { ExportFromStagingError } from './exportFromStagingErrors';
import type { OriginalFallbackReason } from './exportSourcePolicy';
import type { ExportPrepJobRow } from './exportPrepTypes';
import { validateReadyStaging } from './validateReadyStaging';
import { assertSafeExportFileName } from './validateExportFileName';

export type ExportPhotoSource =
  | 'VALIDATED_STAGING'
  | 'CONTROLLED_ORIGINAL_FALLBACK';

export interface ResolvedExportPhoto {
  readonly capturePhotoId: string;
  readonly captureSessionId: string;
  readonly source: ExportPhotoSource;
  readonly uri: string;
  readonly exportFileName: string;
  readonly sizeBytes: number;
  readonly sha256: string;
  readonly sequenceNumber: number;
  readonly displayName: string | null;
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  readonly mimeType: string;
  readonly width: number;
  readonly height: number;
  readonly clientFileId: string;
  readonly getBytes: () => Promise<Uint8Array>;
}

export interface ResolveExportPhotosResult {
  readonly photos: readonly ResolvedExportPhoto[];
  readonly stagingCount: number;
  readonly originalFallbackCount: number;
  readonly fallbackReason: OriginalFallbackReason | null;
  /** True when every packaging photo passed strong READY validation. */
  readonly allStagingStrongValidated: boolean;
}

function assertUniqueFileNames(photos: readonly ResolvedExportPhoto[]): void {
  const seen = new Set<string>();
  for (const p of photos) {
    if (seen.has(p.exportFileName)) {
      throw new ExportFromStagingError(
        'DUPLICATE_EXPORT_FILE_NAME',
        `nombre duplicado ${p.exportFileName}`,
        { photoId: p.capturePhotoId },
      );
    }
    seen.add(p.exportFileName);
  }
}

/**
 * Modern path: every expected packaging photo must have a strongly validated READY job.
 * Never falls back to the gallery original.
 */
export async function resolveExportPhotosFromStaging(input: {
  readonly session: CaptureSessionRow;
  readonly expectedPhotos: readonly CapturePhotoRow[];
  readonly jobsByPhotoId: ReadonlyMap<string, ExportPrepJobRow>;
  readonly prepRepo: ExportPrepRepository;
  readonly invalidateOnFailure?: boolean;
}): Promise<ResolveExportPhotosResult> {
  const {
    session,
    expectedPhotos,
    jobsByPhotoId,
    prepRepo,
    invalidateOnFailure = true,
  } = input;
  const freezeId = session.active_freeze_id;
  const freezeGeneration = session.capture_freeze_generation ?? null;
  const out: ResolvedExportPhoto[] = [];

  for (let i = 0; i < expectedPhotos.length; i += 1) {
    const photo = expectedPhotos[i]!;
    const job = jobsByPhotoId.get(photo.id);
    if (!job) {
      throw new ExportFromStagingError(
        'PREP_JOB_MISSING',
        `falta preparación de exportación para ${photo.id}`,
        { photoId: photo.id },
      );
    }
    if (
      job.capture_session_id &&
      job.capture_session_id !== session.id
    ) {
      throw new ExportFromStagingError(
        'PHOTO_SET_MISMATCH',
        `job de otra sesión para ${photo.id}`,
        { photoId: photo.id },
      );
    }
    if (job.status === 'FAILED_TERMINAL') {
      throw new ExportFromStagingError(
        'PREP_TERMINAL',
        `${photo.id} (${job.error_code ?? 'FAILED_TERMINAL'}). Reintentá o excluí la foto.`,
        { photoId: photo.id },
      );
    }
    if (job.status === 'FAILED_RETRYABLE') {
      throw new ExportFromStagingError(
        'PREP_FAILED_RETRYABLE',
        `${photo.id} (${job.error_code ?? job.status})`,
        { photoId: photo.id },
      );
    }
    if (job.status !== 'READY') {
      throw new ExportFromStagingError(
        'PREP_NOT_READY',
        `${photo.id} aún en ${job.status}`,
        { photoId: photo.id },
      );
    }

    const ready = await validateReadyStaging(job, 'strong');
    if (!ready.ok) {
      const failure = ready.failure ?? 'UNKNOWN';
      if (invalidateOnFailure) {
        await prepRepo.invalidateReady(
          photo.id,
          `EXPORT_PREP_READY_INVALID:${failure}`,
          'READY no pasó validación fuerte en preflight',
        );
      }
      const code =
        failure === 'STAGING_FILE_MISSING' || failure === 'MISSING_STAGING_URI'
          ? 'STAGING_FILE_MISSING'
          : failure === 'STAGING_SIZE_MISMATCH' || failure === 'INVALID_SIZE_BYTES'
            ? 'STAGING_SIZE_MISMATCH'
            : failure === 'STAGING_SHA_MISMATCH' || failure === 'INVALID_SHA256_FORMAT'
              ? 'STAGING_HASH_MISMATCH'
              : 'PREP_NOT_READY';
      throw new ExportFromStagingError(
        code,
        `${photo.id} READY inválido (${failure})`,
        { photoId: photo.id },
      );
    }

    const stagingUri = job.staging_uri!;
    const fileName =
      job.export_file_name ||
      exportPhotoFileName(photo.id, photo.sequence_number ?? i + 1, photo.display_name);
    assertSafeExportFileName(
      fileName,
      photo.id,
      photo.sequence_number ?? i + 1,
      photo.display_name,
    );
    const expectedSha = (job.sha256 ?? '').trim().toLowerCase();
    const expectedSize = job.size_bytes ?? 0;

    out.push({
      capturePhotoId: photo.id,
      captureSessionId: session.id,
      source: 'VALIDATED_STAGING',
      uri: stagingUri,
      exportFileName: fileName,
      sizeBytes: expectedSize,
      sha256: expectedSha,
      sequenceNumber: photo.sequence_number ?? i + 1,
      displayName: photo.display_name,
      freezeId,
      freezeGeneration,
      mimeType: photo.mime_type || 'image/jpeg',
      width: photo.width ?? 0,
      height: photo.height ?? 0,
      clientFileId: photo.client_file_id ?? photo.id,
      getBytes: async () => {
        const b64 = await FileSystem.readAsStringAsync(stagingUri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        const bytes = base64ToUint8Array(b64);
        if (bytes.byteLength === 0) {
          throw new ExportFromStagingError(
            'PACKAGE_VALIDATION_FAILED',
            `photo vacía ${photo.id}`,
            { photoId: photo.id },
          );
        }
        if (bytes.byteLength !== expectedSize) {
          await prepRepo.invalidateReady(
            photo.id,
            'EXPORT_PREP_SIZE_MISMATCH',
            `size ${bytes.byteLength} != ${expectedSize}`,
          );
          throw new ExportFromStagingError(
            'STAGING_SIZE_MISMATCH',
            `tamaño no coincide para ${photo.id}`,
            { photoId: photo.id },
          );
        }
        const sha = sha256BytesHex(bytes);
        if (sha !== expectedSha) {
          await prepRepo.invalidateReady(
            photo.id,
            'EXPORT_PREP_SHA_MISMATCH',
            'sha256 mismatch',
          );
          throw new ExportFromStagingError(
            'STAGING_HASH_MISMATCH',
            `sha256 no coincide para ${photo.id}`,
            { photoId: photo.id },
          );
        }
        return bytes;
      },
    });
  }

  if (out.length !== expectedPhotos.length) {
    throw new ExportFromStagingError(
      'PHOTO_SET_MISMATCH',
      `resueltas ${out.length} != esperadas ${expectedPhotos.length}`,
    );
  }
  assertUniqueFileNames(out);
  return {
    photos: out,
    stagingCount: out.length,
    originalFallbackCount: 0,
    fallbackReason: null,
    allStagingStrongValidated: true,
  };
}

/**
 * Legacy / flag-off path: read MediaStore originals with real hash/size and deterministic names.
 */
export async function resolveExportPhotosFromOriginals(input: {
  readonly session: CaptureSessionRow;
  readonly expectedPhotos: readonly CapturePhotoRow[];
  readonly fallbackReason: OriginalFallbackReason;
}): Promise<ResolveExportPhotosResult> {
  const { session, expectedPhotos, fallbackReason } = input;
  const freezeId = session.active_freeze_id;
  const freezeGeneration = session.capture_freeze_generation ?? null;
  const out: ResolvedExportPhoto[] = [];

  for (let i = 0; i < expectedPhotos.length; i += 1) {
    const photo = expectedPhotos[i]!;
    const seq = photo.sequence_number ?? i + 1;
    const name = exportPhotoFileName(photo.id, seq, photo.display_name);
    assertSafeExportFileName(name, photo.id, seq, photo.display_name);
    const sourceUri = photo.uri;
    let cached: Uint8Array | null = null;
    const load = async (): Promise<Uint8Array> => {
      if (cached) return cached;
      try {
        const info = await FileSystem.getInfoAsync(sourceUri, { size: true });
        if (!info.exists || typeof info.size !== 'number' || info.size <= 0) {
          throw new Error('original missing or empty');
        }
        const b64 = await FileSystem.readAsStringAsync(sourceUri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        cached = base64ToUint8Array(b64);
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          `no se pudo leer la foto ${photo.id} (${name}): ${detail}`,
          { photoId: photo.id },
        );
      }
      if (cached.byteLength === 0) {
        throw new ExportFromStagingError(
          'PACKAGE_VALIDATION_FAILED',
          `foto vacía ${photo.id} (${name})`,
          { photoId: photo.id },
        );
      }
      return cached;
    };
    const bytes = await load();
    out.push({
      capturePhotoId: photo.id,
      captureSessionId: session.id,
      source: 'CONTROLLED_ORIGINAL_FALLBACK',
      uri: sourceUri,
      exportFileName: name,
      sizeBytes: bytes.byteLength,
      sha256: sha256BytesHex(bytes),
      sequenceNumber: seq,
      displayName: photo.display_name,
      freezeId,
      freezeGeneration,
      mimeType: photo.mime_type || 'image/jpeg',
      width: photo.width ?? 0,
      height: photo.height ?? 0,
      clientFileId: photo.client_file_id ?? photo.id,
      getBytes: load,
    });
  }

  assertUniqueFileNames(out);
  return {
    photos: out,
    stagingCount: 0,
    originalFallbackCount: out.length,
    fallbackReason,
    allStagingStrongValidated: false,
  };
}
