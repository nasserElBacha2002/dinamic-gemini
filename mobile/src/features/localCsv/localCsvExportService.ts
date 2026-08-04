import * as FileSystem from 'expo-file-system';
import { Share } from 'react-native';

import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import type { LocalCsvExportRepository } from '../../database/repositories/localCsvExportRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import { createId } from '../../shared/createId';
import { buildLocalCsvExport } from './buildLocalCsvExport';
import { sha256Hex } from './csvFormat';

export interface LocalCsvExportServiceDeps {
  readonly captureRepo: CaptureRepository;
  readonly draftRepo: LocalDetectionDraftRepository;
  readonly confirmedRepo: ConfirmedLocalResultRepository;
  readonly exportRepo: LocalCsvExportRepository;
  readonly deviceId: string;
  readonly companyId?: string | null;
  readonly clientId?: string | null;
  readonly enabled?: boolean;
}

export interface ExportedLocalCsv {
  readonly exportId: string;
  readonly fileUri: string;
  readonly checksumSha256: string;
  readonly rowCount: number;
  readonly reused: boolean;
}

export class LocalCsvExportService {
  constructor(private readonly deps: LocalCsvExportServiceDeps) {}

  async exportSession(sessionId: string): Promise<ExportedLocalCsv> {
    if (this.deps.enabled === false) {
      throw new Error('La exportación CSV local no está habilitada.');
    }
    const session = await this.deps.captureRepo.getSession(sessionId);
    if (!session) {
      throw new Error('No se encontró la captura local.');
    }
    // Prefer exact freeze snapshot; never invent a live set when freeze exists.
    let photos = await this.deps.captureRepo.listPhotos(sessionId);
    if (session.active_freeze_id) {
      photos = await this.deps.captureRepo.listFreezePhotos(session.active_freeze_id);
    }
    const drafts = await this.deps.draftRepo.listForSession(sessionId).catch(() => []);
    const confirmed = await this.deps.confirmedRepo.listForSession(sessionId).catch(() => []);

    const built = await buildLocalCsvExport({
      session,
      photos,
      drafts,
      confirmed,
      deviceId: this.deps.deviceId,
      companyId: this.deps.companyId ?? null,
      clientId: this.deps.clientId ?? null,
      freezeId: session.active_freeze_id,
      freezeGeneration: session.capture_freeze_generation,
    });

    const contentFingerprint = await sha256Hex(
      `${sessionId}|${built.rowCount}|${built.csv.length}|${built.checksumSha256}`,
    );
    const existing = await this.deps.exportRepo.findByFingerprint(contentFingerprint);
    if (existing?.file_uri) {
      const info = await FileSystem.getInfoAsync(existing.file_uri);
      if (info.exists) {
        return {
          exportId: existing.export_id,
          fileUri: existing.file_uri,
          checksumSha256: existing.checksum_sha256,
          rowCount: existing.row_count,
          reused: true,
        };
      }
    }

    const dir = `${FileSystem.cacheDirectory ?? FileSystem.documentDirectory}csv-exports/`;
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
    const tmpUri = `${dir}${built.exportId}.tmp.csv`;
    const finalUri = `${dir}${built.exportId}.csv`;
    await FileSystem.writeAsStringAsync(tmpUri, built.csv, {
      encoding: FileSystem.EncodingType.UTF8,
    });
    await FileSystem.moveAsync({ from: tmpUri, to: finalUri });

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
      file_uri: finalUri,
      freeze_id: built.freezeId,
      exported_at: built.exportedAt,
      shared_at: null,
      created_at: now,
      updated_at: now,
    });

    return {
      exportId: built.exportId,
      fileUri: finalUri,
      checksumSha256: built.checksumSha256,
      rowCount: built.rowCount,
      reused: false,
    };
  }

  async shareExport(fileUri: string, exportId: string): Promise<void> {
    await Share.share({
      url: fileUri,
      message: `Exportación local Dinamic Inventory (${exportId})`,
      title: 'Exportar resultados CSV',
    });
    await this.deps.exportRepo.markShared(exportId, new Date().toISOString());
  }
}
