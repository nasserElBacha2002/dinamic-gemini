import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import { sha256BytesHex } from '../../core/payloadFingerprint';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { createId } from '../../shared/createId';
import type { LocalCsvExportService } from '../localCsv/localCsvExportService';
import { base64ToUint8Array, uint8ArrayToBase64 } from '../localCsv/binaryCodec';
import { buildZipBytes, type ZipEntrySource } from './boundedMemoryZipWriter';
import {
  collectProfileEntries,
  finalizeCaptureRawHashes,
  mapPhotoToCapture,
  sortCapturesDeterministic,
} from './captureMapper';
import {
  OFFLINE_AISLE_EXPORT_DIR,
  OFFLINE_AISLE_FORMAT,
  OFFLINE_AISLE_SCHEMA_VERSION,
} from './constants';
import { OfflineAisleExportError } from './errors';
import {
  buildManifestWithIntegrity,
  computePackageIntegrity,
  stableJson,
  validatePackageModel,
  type OfflineAislePackageModel,
} from './packageValidator';
import { buildDinamicArchiveFileName } from './sanitizeFileName';
import { selectLatestSession } from './sessionSelection';
import type { OfflineAisleCaptureV1, OfflineAisleDocumentV1, PackageCompleteness } from './types';

export interface OfflineAisleExportServiceDeps {
  readonly catalogRepo: LocalCatalogRepository;
  readonly captureRepo: CaptureRepository;
  readonly draftRepo: LocalDetectionDraftRepository;
  readonly listSessionsForAisle: (aisleId: string) => Promise<readonly CaptureSessionRow[]>;
  readonly sessionCsvExport?: LocalCsvExportService | null;
  readonly appVersion: string;
  readonly enabled?: boolean;
}

export interface ExportAisleOptions {
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly includeAssets?: boolean;
  readonly requireAssets?: boolean;
}

export interface ExportedOfflineAisle {
  readonly exportId: string;
  readonly fileUri: string;
  readonly fileName: string;
  readonly captureCount: number;
  readonly assetCount: number;
  readonly completeness: PackageCompleteness;
}

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

export class OfflineAisleExportService {
  private readonly inFlight = new Set<string>();

  constructor(private readonly deps: OfflineAisleExportServiceDeps) {}

  async exportAisle(options: ExportAisleOptions): Promise<ExportedOfflineAisle> {
    if (this.deps.enabled === false) {
      throw new OfflineAisleExportError('AISLE_NOT_EXPORTABLE', 'export deshabilitado');
    }
    const key = `${options.inventoryId}:${options.aisleId}`;
    if (this.inFlight.has(key)) {
      throw new OfflineAisleExportError('EXPORT_IN_PROGRESS', 'export ya en curso');
    }
    this.inFlight.add(key);
    const exportId = createId();
    const tmpBase = `${FileSystem.cacheDirectory ?? FileSystem.documentDirectory}${OFFLINE_AISLE_EXPORT_DIR}/tmp-${exportId}`;
    try {
      return await this.exportAisleInner(options, exportId, tmpBase);
    } finally {
      this.inFlight.delete(key);
      await FileSystem.deleteAsync(tmpBase, { idempotent: true }).catch(() => undefined);
    }
  }

  async shareExport(fileUri: string, _fileName: string): Promise<void> {
    const available = await Sharing.isAvailableAsync();
    if (!available) {
      throw new OfflineAisleExportError('PACKAGE_WRITE_FAILED', 'share no disponible');
    }
    await Sharing.shareAsync(fileUri, {
      mimeType: 'application/zip',
      dialogTitle: 'Exportar pasillo offline',
      UTI: 'public.zip-archive',
    });
  }

  private async exportAisleInner(
    options: ExportAisleOptions,
    exportId: string,
    tmpBase: string,
  ): Promise<ExportedOfflineAisle> {
    const includeAssets = options.includeAssets !== false;
    const requireAssets = options.requireAssets === true;

    const aisleRow = await this.deps.catalogRepo.getAisleById(options.inventoryId, options.aisleId);
    if (!aisleRow) {
      throw new OfflineAisleExportError('AISLE_NOT_FOUND', options.aisleId);
    }
    if (aisleRow.sync_status !== 'LOCAL_ONLY') {
      throw new OfflineAisleExportError(
        'AISLE_NOT_EXPORTABLE',
        'solo pasillos LOCAL_ONLY en Fase 4',
      );
    }

    const inventory = await this.deps.catalogRepo.getInventoryById(options.inventoryId);
    if (!inventory) {
      throw new OfflineAisleExportError('INVENTORY_NOT_FOUND', options.inventoryId);
    }

    let supplierName: string | null = null;
    if (aisleRow.client_supplier_id && inventory.client_id) {
      const supplier = await this.deps.catalogRepo.getSupplierById(
        inventory.client_id,
        aisleRow.client_supplier_id,
      );
      supplierName = supplier?.name ?? null;
    }

    const sessions = await this.deps.listSessionsForAisle(options.aisleId);
    const sessionSnapshot = [...sessions];
    if (sessionSnapshot.length === 0) {
      throw new OfflineAisleExportError('NO_CAPTURES', 'sin sesiones de captura');
    }

    const photos: CapturePhotoRow[] = [];
    const draftByPhoto = new Map<
      string,
      Awaited<ReturnType<LocalDetectionDraftRepository['listForSession']>>[number]
    >();

    for (const session of sessionSnapshot) {
      if (this.deps.sessionCsvExport) {
        await this.deps.sessionCsvExport.prepareSessionForExport(session.id);
      }
      let sessionPhotos = await this.deps.captureRepo.listPhotos(session.id);
      if (session.active_freeze_id) {
        sessionPhotos = await this.deps.captureRepo.listFreezePhotos(session.active_freeze_id);
      }
      for (const p of sessionPhotos.filter(
        (ph) => ph.status !== 'excluded' && ph.status !== 'rejected',
      )) {
        photos.push(p);
      }
      const drafts = await this.deps.draftRepo.listForSession(session.id);
      for (const d of drafts) {
        draftByPhoto.set(d.capture_photo_id, d);
      }
    }

    if (photos.length === 0) {
      throw new OfflineAisleExportError('NO_CAPTURES', 'sin fotos elegibles');
    }

    const sessionById = new Map(sessionSnapshot.map((s) => [s.id, s]));
    const mapped: OfflineAisleCaptureV1[] = [];
    for (const photo of photos) {
      const session = sessionById.get(photo.capture_session_id);
      if (!session) continue;
      mapped.push(
        mapPhotoToCapture({
          photo,
          session,
          aisleId: options.aisleId,
          aisleClientSupplierId: aisleRow.client_supplier_id,
          draft: draftByPhoto.get(photo.id),
          includeAssets,
          requireAssets,
        }),
      );
    }

    const captures = await finalizeCaptureRawHashes(sortCapturesDeterministic(mapped));
    const profiles = collectProfileEntries(captures);

    const assetHashes: Record<string, string> = {};
    const assetUriByPath = new Map<string, string>();
    let assetCount = 0;
    let anyAssetMissing = false;
    const finalCaptures: OfflineAisleCaptureV1[] = [];

    if (includeAssets) {
      for (const cap of captures) {
        if (!cap.asset?.path) {
          finalCaptures.push(cap);
          continue;
        }
        const photo = photos.find((p) => p.id === cap.capture_id);
        if (!photo) {
          finalCaptures.push(cap);
          continue;
        }
        try {
          const b64 = await FileSystem.readAsStringAsync(photo.uri, {
            encoding: FileSystem.EncodingType.Base64,
          });
          const bytes = base64ToUint8Array(b64);
          if (bytes.byteLength === 0) {
            if (requireAssets) {
              throw new OfflineAisleExportError('ASSET_MISSING', cap.capture_id);
            }
            anyAssetMissing = true;
            finalCaptures.push({
              ...cap,
              asset: {
                ...cap.asset,
                included: false,
                path: null,
                size_bytes: null,
                sha256: null,
                asset_missing: true,
              },
            });
            continue;
          }
          const hash = sha256BytesHex(bytes);
          assetHashes[cap.asset.path] = hash;
          assetUriByPath.set(cap.asset.path, photo.uri);
          assetCount += 1;
          finalCaptures.push({
            ...cap,
            asset: {
              ...cap.asset,
              size_bytes: bytes.byteLength,
              sha256: hash,
            },
          });
        } catch (err) {
          if (requireAssets) {
            throw new OfflineAisleExportError(
              'ASSET_MISSING',
              `${cap.capture_id}: ${err instanceof Error ? err.message : String(err)}`,
            );
          }
          anyAssetMissing = true;
          finalCaptures.push({
            ...cap,
            asset: {
              ...cap.asset,
              included: false,
              path: null,
              size_bytes: null,
              sha256: null,
              asset_missing: true,
            },
          });
        }
      }
    } else {
      finalCaptures.push(...captures);
    }

    const latestSession = selectLatestSession(sessionSnapshot);
    const aisleDoc: OfflineAisleDocumentV1 = {
      id: aisleRow.id,
      inventory_id: aisleRow.inventory_id,
      client_supplier_id: aisleRow.client_supplier_id,
      name: aisleRow.code,
      created_offline_at: aisleRow.created_offline_at,
      completed_at: latestSession.finished_at ?? latestSession.capture_frozen_at,
      origin: aisleRow.origin,
      sync_status: aisleRow.sync_status,
    };

    const captureFiles: Record<string, string> = {};
    for (const cap of finalCaptures) {
      captureFiles[`captures/${cap.capture_id}.json`] = stableJson(cap);
    }

    const hasReviewIssues = finalCaptures.some(
      (c) => c.result_kind === 'UNRECOGNIZED' || c.requires_review,
    );
    const completeness: PackageCompleteness =
      hasReviewIssues || anyAssetMissing ? 'PARTIAL' : 'COMPLETE';

    const manifestBase = {
      format: OFFLINE_AISLE_FORMAT,
      schema_version: OFFLINE_AISLE_SCHEMA_VERSION,
      export_id: exportId,
      created_at: new Date().toISOString(),
      app_version: this.deps.appVersion,
      inventory: {
        id: inventory.id,
        name: inventory.name,
        client_id: inventory.client_id,
      },
      aisle: {
        id: aisleRow.id,
        name: aisleRow.code,
        origin: aisleRow.origin,
        sync_status: aisleRow.sync_status,
        operational_status: latestSession.status,
      },
      supplier: {
        client_supplier_id: aisleRow.client_supplier_id,
        name: supplierName,
      },
      capture_count: finalCaptures.length,
      asset_count: assetCount,
      include_assets: includeAssets,
      completeness,
    };

    const integrityFiles = await computePackageIntegrity({
      manifest: buildManifestWithIntegrity(manifestBase, {}),
      aisle: aisleDoc,
      profiles,
      captures: finalCaptures,
      captureFiles,
      assetHashes,
    });

    const manifest = buildManifestWithIntegrity(manifestBase, integrityFiles);
    const model: OfflineAislePackageModel = {
      manifest,
      aisle: aisleDoc,
      profiles,
      captures: finalCaptures,
      captureFiles,
      assetHashes,
    };
    await validatePackageModel(model);

    const zipEntries: ZipEntrySource[] = [
      { path: 'manifest.json', getBytes: () => utf8Encode(stableJson(manifest)) },
      { path: 'aisle.json', getBytes: () => utf8Encode(stableJson(aisleDoc)) },
      {
        path: 'recognition/profiles.json',
        getBytes: () => utf8Encode(stableJson(profiles)),
      },
    ];
    for (const [path, content] of Object.entries(captureFiles)) {
      zipEntries.push({ path, getBytes: () => utf8Encode(content) });
    }
    for (const [path, uri] of assetUriByPath.entries()) {
      zipEntries.push({
        path,
        getBytes: async () => {
          const b64 = await FileSystem.readAsStringAsync(uri, {
            encoding: FileSystem.EncodingType.Base64,
          });
          return base64ToUint8Array(b64);
        },
      });
    }

    const zipped = await buildZipBytes(zipEntries);
    const fileName = buildDinamicArchiveFileName(aisleRow.code, aisleRow.id);
    const outDir = `${FileSystem.documentDirectory ?? FileSystem.cacheDirectory}${OFFLINE_AISLE_EXPORT_DIR}/`;
    await FileSystem.makeDirectoryAsync(outDir, { intermediates: true }).catch(() => undefined);
    const fileUri = `${outDir}${fileName}`;
    const tmpUri = `${tmpBase}.dinamic`;
    await FileSystem.makeDirectoryAsync(tmpBase, { intermediates: true }).catch(() => undefined);
    await FileSystem.writeAsStringAsync(tmpUri, uint8ArrayToBase64(zipped), {
      encoding: FileSystem.EncodingType.Base64,
    });
    await FileSystem.deleteAsync(fileUri, { idempotent: true }).catch(() => undefined);
    await FileSystem.moveAsync({ from: tmpUri, to: fileUri });

    return {
      exportId,
      fileUri,
      fileName,
      captureCount: finalCaptures.length,
      assetCount,
      completeness,
    };
  }
}
