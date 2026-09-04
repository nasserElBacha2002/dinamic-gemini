import { sha256Hex } from '../localCsv/csvFormat';
import type {
  OfflineAisleCaptureV1,
  OfflineAisleDocumentV1,
  OfflineAisleKindProvenance,
  OfflineAisleManifestV1,
  OfflineAisleProfileEntryV1,
} from './types';
import { OFFLINE_AISLE_FORMAT, OFFLINE_AISLE_SCHEMA_VERSION } from './constants';
import { OfflineAisleExportError } from './errors';

export interface OfflineAislePackageModel {
  readonly manifest: OfflineAisleManifestV1;
  readonly aisle: OfflineAisleDocumentV1;
  readonly profiles: readonly OfflineAisleProfileEntryV1[];
  readonly captures: readonly OfflineAisleCaptureV1[];
  readonly captureFiles: Readonly<Record<string, string>>;
  /** SHA-256 hex per included asset path (no raw bytes retained). */
  readonly assetHashes: Readonly<Record<string, string>>;
}

function stableJson(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

export function buildExpectedIntegrityPaths(model: OfflineAislePackageModel): Set<string> {
  const expected = new Set<string>(['aisle.json', 'recognition/profiles.json']);
  for (const path of Object.keys(model.captureFiles)) {
    expected.add(path);
  }
  for (const cap of model.captures) {
    if (cap.asset?.included && cap.asset.path) {
      expected.add(cap.asset.path);
    }
  }
  return expected;
}

export async function computePackageIntegrity(
  model: OfflineAislePackageModel,
): Promise<Record<string, string>> {
  const files: Record<string, string> = {};
  files['aisle.json'] = await sha256Hex(stableJson(model.aisle));
  files['recognition/profiles.json'] = await sha256Hex(stableJson(model.profiles));
  for (const [path, content] of Object.entries(model.captureFiles)) {
    files[path] = await sha256Hex(content);
  }
  for (const [path, hash] of Object.entries(model.assetHashes)) {
    files[path] = hash;
  }
  return files;
}

async function validateRawHash(
  captureId: string,
  kind: string,
  provenance: OfflineAisleKindProvenance | null,
): Promise<void> {
  if (!provenance) return;
  const raw = provenance.raw_evidence.raw_payload;
  const expected = provenance.raw_evidence.raw_payload_sha256;
  if (!raw || !expected) return;
  const actual = await sha256Hex(raw);
  if (actual !== expected) {
    throw new OfflineAisleExportError(
      'PACKAGE_HASH_FAILED',
      `raw hash mismatch (${kind}) en capture ${captureId}`,
    );
  }
}

function validateRawNotSku(
  captureId: string,
  provenance: OfflineAisleKindProvenance | null,
  sku: string | null | undefined,
): void {
  const raw = provenance?.raw_evidence.raw_payload ?? '';
  if (raw && sku && sku === raw) {
    throw new OfflineAisleExportError(
      'RAW_EVIDENCE_MISSING',
      `sku no puede ser raw payload (${captureId})`,
    );
  }
}

export async function validatePackageModel(model: OfflineAislePackageModel): Promise<void> {
  if (model.manifest.format !== OFFLINE_AISLE_FORMAT) {
    throw new OfflineAisleExportError('PACKAGE_HASH_FAILED', 'format inválido');
  }
  if (model.manifest.schema_version !== OFFLINE_AISLE_SCHEMA_VERSION) {
    throw new OfflineAisleExportError('PACKAGE_HASH_FAILED', 'schema_version inválido');
  }

  if (model.manifest.capture_count !== model.captures.length) {
    throw new OfflineAisleExportError(
      'PACKAGE_HASH_FAILED',
      `capture_count mismatch: manifest=${model.manifest.capture_count} actual=${model.captures.length}`,
    );
  }

  const includedAssets = model.captures.filter((c) => c.asset?.included).length;
  if (model.manifest.asset_count !== includedAssets) {
    throw new OfflineAisleExportError(
      'PACKAGE_HASH_FAILED',
      `asset_count mismatch: manifest=${model.manifest.asset_count} actual=${includedAssets}`,
    );
  }

  const captureIds = new Set<string>();
  for (const cap of model.captures) {
    if (captureIds.has(cap.capture_id)) {
      throw new OfflineAisleExportError(
        'CAPTURE_ID_DUPLICATED',
        `capture_id duplicado: ${cap.capture_id}`,
      );
    }
    captureIds.add(cap.capture_id);
    if (cap.aisle_id !== model.aisle.id) {
      throw new OfflineAisleExportError(
        'CAPTURE_AISLE_MISMATCH',
        `capture ${cap.capture_id} aisle mismatch`,
      );
    }
    const expectedPath = `captures/${cap.capture_id}.json`;
    if (!model.captureFiles[expectedPath]) {
      throw new OfflineAisleExportError('PACKAGE_HASH_FAILED', `falta ${expectedPath}`);
    }

    for (const prov of [cap.recognitions.item, cap.recognitions.position]) {
      if (
        prov?.client_supplier_id &&
        model.aisle.client_supplier_id &&
        prov.client_supplier_id !== model.aisle.client_supplier_id
      ) {
        throw new OfflineAisleExportError(
          'SUPPLIER_METADATA_INCOMPLETE',
          `supplier mismatch en capture ${cap.capture_id}`,
        );
      }
    }

    await validateRawHash(cap.capture_id, 'item', cap.recognitions.item);
    await validateRawHash(cap.capture_id, 'position', cap.recognitions.position);

    if (cap.result_kind !== 'UNRECOGNIZED' && cap.recognitions.item) {
      validateRawNotSku(cap.capture_id, cap.recognitions.item, cap.result.product?.sku);
    }

    if (cap.result_kind === 'POSITION_ONLY' && cap.result.product != null) {
      const hasSku = Boolean((cap.result.product.sku ?? '').trim());
      if (hasSku) {
        throw new OfflineAisleExportError(
          'RAW_EVIDENCE_MISSING',
          `POSITION_ONLY no debe incluir producto (${cap.capture_id})`,
        );
      }
    }

    if (cap.asset?.included && cap.asset.path) {
      if (!model.assetHashes[cap.asset.path]) {
        throw new OfflineAisleExportError(
          'ASSET_MISSING',
          `asset faltante para capture ${cap.capture_id}`,
        );
      }
    }
    if (cap.asset?.asset_missing && cap.asset.included) {
      throw new OfflineAisleExportError(
        'ASSET_MISSING',
        `asset marcado included pero missing (${cap.capture_id})`,
      );
    }
  }

  const integrity = await computePackageIntegrity(model);
  const expectedPaths = buildExpectedIntegrityPaths(model);
  const manifestPaths = new Set(Object.keys(model.manifest.integrity.files));

  for (const path of expectedPaths) {
    if (!manifestPaths.has(path)) {
      throw new OfflineAisleExportError(
        'PACKAGE_HASH_FAILED',
        `falta hash en manifest: ${path}`,
      );
    }
  }
  for (const path of manifestPaths) {
    if (!expectedPaths.has(path)) {
      throw new OfflineAisleExportError(
        'PACKAGE_HASH_FAILED',
        `hash inesperado en manifest: ${path}`,
      );
    }
  }

  for (const [path, hash] of Object.entries(integrity)) {
    if (model.manifest.integrity.files[path] !== hash) {
      throw new OfflineAisleExportError(
        'PACKAGE_HASH_FAILED',
        `hash mismatch ${path}`,
      );
    }
  }
}

export function buildManifestWithIntegrity(
  base: Omit<OfflineAisleManifestV1, 'integrity'>,
  files: Record<string, string>,
): OfflineAisleManifestV1 {
  return {
    ...base,
    integrity: {
      algorithm: 'sha256',
      files,
    },
  };
}

export { stableJson };
