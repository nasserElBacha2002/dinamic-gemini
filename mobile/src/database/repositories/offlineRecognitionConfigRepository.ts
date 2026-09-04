import type { SQLiteDatabase } from 'expo-sqlite';
import type {
  OfflineAisleRecognitionConfigDto,
  OfflineRecognitionBundleDto,
  OfflineRecognitionProfileDto,
} from '../../features/offlineRecognition/types';
import { assertCompatibleBundle } from '../../features/offlineRecognition/types';

export interface OfflineRecognitionProfileRow {
  inventory_id: string;
  client_supplier_id: string;
  label_kind: 'ITEM' | 'POSITION';
  source: string;
  profile_id: string;
  profile_version: number;
  configuration_schema_version: number;
  recognition_mode: string | null;
  semantic_type: string | null;
  configuration_json: string;
  synced_at: string;
}

export interface OfflineAisleRecognitionConfigRow {
  inventory_id: string;
  aisle_id: string;
  client_supplier_id: string | null;
  item_profile_source_override: string | null;
  position_profile_source_override: string | null;
  effective_item_source: string;
  effective_position_source: string;
  synced_at: string;
}

export interface OfflineSupplierRecognitionConfigRow {
  inventory_id: string;
  client_supplier_id: string;
  item_source: string;
  position_source: string;
  synced_at: string;
}

export interface OfflineRecognitionSyncMetaRow {
  inventory_id: string;
  client_id: string;
  bundle_schema_version: number;
  bundle_revision: string | null;
  synced_at: string;
  generated_at: string | null;
}

export class OfflineRecognitionConfigRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async getSyncMeta(inventoryId: string): Promise<OfflineRecognitionSyncMetaRow | null> {
    const row = await this.db.getFirstAsync<OfflineRecognitionSyncMetaRow>(
      `SELECT inventory_id, client_id, bundle_schema_version, bundle_revision, synced_at, generated_at
       FROM offline_recognition_sync_meta WHERE inventory_id = ?`,
      [inventoryId],
    );
    return row ?? null;
  }

  async getAisleConfig(
    inventoryId: string,
    aisleId: string,
  ): Promise<OfflineAisleRecognitionConfigRow | null> {
    const row = await this.db.getFirstAsync<OfflineAisleRecognitionConfigRow>(
      `SELECT * FROM offline_aisle_recognition_config
       WHERE inventory_id = ? AND aisle_id = ?`,
      [inventoryId, aisleId],
    );
    return row ?? null;
  }

  async getProfile(
    inventoryId: string,
    clientSupplierId: string,
    labelKind: 'ITEM' | 'POSITION',
  ): Promise<OfflineRecognitionProfileRow | null> {
    const row = await this.db.getFirstAsync<OfflineRecognitionProfileRow>(
      `SELECT * FROM offline_recognition_profiles
       WHERE inventory_id = ? AND client_supplier_id = ? AND label_kind = ?`,
      [inventoryId, clientSupplierId, labelKind],
    );
    return row ?? null;
  }

  async getSupplierBaseSources(
    inventoryId: string,
    clientSupplierId: string,
  ): Promise<{ item_source: 'DINAMIC' | 'SUPPLIER'; position_source: 'DINAMIC' | 'SUPPLIER' } | null> {
    const row = await this.db.getFirstAsync<OfflineSupplierRecognitionConfigRow>(
      `SELECT inventory_id, client_supplier_id, item_source, position_source, synced_at
       FROM offline_supplier_recognition_config
       WHERE inventory_id = ? AND client_supplier_id = ?`,
      [inventoryId, clientSupplierId],
    );
    if (!row) {
      return null;
    }
    const item = (row.item_source || '').toUpperCase();
    const position = (row.position_source || '').toUpperCase();
    if (item !== 'DINAMIC' && item !== 'SUPPLIER') {
      return null;
    }
    if (position !== 'DINAMIC' && position !== 'SUPPLIER') {
      return null;
    }
    return {
      item_source: item as 'DINAMIC' | 'SUPPLIER',
      position_source: position as 'DINAMIC' | 'SUPPLIER',
    };
  }

  async listProfiles(inventoryId: string): Promise<OfflineRecognitionProfileRow[]> {
    return this.db.getAllAsync<OfflineRecognitionProfileRow>(
      `SELECT * FROM offline_recognition_profiles WHERE inventory_id = ?`,
      [inventoryId],
    );
  }

  /**
   * Atomic replace of aisle mappings + profiles for one inventory.
   * On failure the previous committed state remains (caller catches).
   */
  async replaceBundle(bundle: OfflineRecognitionBundleDto, syncedAtIso: string): Promise<void> {
    assertCompatibleBundle(bundle);
    const preservedProfiles = await this.loadDraftReferencedProfiles(bundle.inventory_id);
    const newProfileKeys = new Set(
      bundle.profiles.map(
        (profile) => profileKey(bundle.inventory_id, profile.client_supplier_id, profile.label_kind),
      ),
    );
    await this.db.withTransactionAsync(async () => {
      await this.db.runAsync(
        `DELETE FROM offline_recognition_profiles WHERE inventory_id = ?`,
        [bundle.inventory_id],
      );
      await this.db.runAsync(
        `DELETE FROM offline_aisle_recognition_config WHERE inventory_id = ?`,
        [bundle.inventory_id],
      );
      await this.db.runAsync(
        `DELETE FROM offline_supplier_recognition_config WHERE inventory_id = ?`,
        [bundle.inventory_id],
      );

      for (const aisle of bundle.aisles) {
        await this.insertAisle(bundle.inventory_id, aisle, syncedAtIso);
      }
      for (const supplier of bundle.suppliers ?? []) {
        await this.insertSupplier(bundle.inventory_id, supplier, syncedAtIso);
      }
      for (const profile of bundle.profiles) {
        await this.insertProfile(bundle.inventory_id, profile, syncedAtIso);
      }
      for (const [key, row] of preservedProfiles.entries()) {
        if (!newProfileKeys.has(key)) {
          await this.insertProfileRow(row);
        }
      }

      await this.db.runAsync(
        `INSERT INTO offline_recognition_sync_meta
          (inventory_id, client_id, bundle_schema_version, bundle_revision, synced_at, generated_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(inventory_id) DO UPDATE SET
           client_id = excluded.client_id,
           bundle_schema_version = excluded.bundle_schema_version,
           bundle_revision = excluded.bundle_revision,
           synced_at = excluded.synced_at,
           generated_at = excluded.generated_at`,
        [
          bundle.inventory_id,
          bundle.client_id,
          bundle.bundle_schema_version,
          bundle.bundle_revision ?? null,
          syncedAtIso,
          bundle.generated_at ?? null,
        ],
      );
    });
  }

  private async insertAisle(
    inventoryId: string,
    aisle: OfflineAisleRecognitionConfigDto,
    syncedAt: string,
  ): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO offline_aisle_recognition_config (
         inventory_id, aisle_id, client_supplier_id,
         item_profile_source_override, position_profile_source_override,
         effective_item_source, effective_position_source, synced_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        inventoryId,
        aisle.aisle_id,
        aisle.client_supplier_id ?? null,
        aisle.item_profile_source_override ?? null,
        aisle.position_profile_source_override ?? null,
        aisle.effective_item_source,
        aisle.effective_position_source,
        syncedAt,
      ],
    );
  }

  private async insertSupplier(
    inventoryId: string,
    supplier: {
      client_supplier_id: string;
      item_source: 'DINAMIC' | 'SUPPLIER';
      position_source: 'DINAMIC' | 'SUPPLIER';
    },
    syncedAt: string,
  ): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO offline_supplier_recognition_config (
         inventory_id, client_supplier_id, item_source, position_source, synced_at
       ) VALUES (?, ?, ?, ?, ?)`,
      [
        inventoryId,
        supplier.client_supplier_id,
        supplier.item_source,
        supplier.position_source,
        syncedAt,
      ],
    );
  }

  private async insertProfile(
    inventoryId: string,
    profile: OfflineRecognitionProfileDto,
    syncedAt: string,
  ): Promise<void> {
    await this.insertProfileRow({
      inventory_id: inventoryId,
      client_supplier_id: profile.client_supplier_id,
      label_kind: profile.label_kind,
      source: profile.source,
      profile_id: profile.profile_id,
      profile_version: profile.profile_version,
      configuration_schema_version: profile.configuration_schema_version,
      recognition_mode: profile.recognition_mode ?? null,
      semantic_type: profile.semantic_type ?? null,
      configuration_json: JSON.stringify(profile.configuration ?? {}),
      synced_at: syncedAt,
    });
  }

  private async insertProfileRow(row: OfflineRecognitionProfileRow): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO offline_recognition_profiles (
         inventory_id, client_supplier_id, label_kind, source,
         profile_id, profile_version, configuration_schema_version,
         recognition_mode, semantic_type, configuration_json, synced_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        row.inventory_id,
        row.client_supplier_id,
        row.label_kind,
        row.source,
        row.profile_id,
        row.profile_version,
        row.configuration_schema_version,
        row.recognition_mode,
        row.semantic_type,
        row.configuration_json,
        row.synced_at,
      ],
    );
  }

  private async loadDraftReferencedProfiles(
    inventoryId: string,
  ): Promise<Map<string, OfflineRecognitionProfileRow>> {
    const rows = await this.db.getAllAsync<{ recognition_profile_snapshot_json: string | null }>(
      `SELECT d.recognition_profile_snapshot_json
       FROM local_detection_drafts d
       INNER JOIN capture_photos p ON p.id = d.capture_photo_id
       INNER JOIN capture_sessions s ON s.id = p.capture_session_id
       WHERE s.inventory_id = ?
         AND d.recognition_profile_snapshot_json IS NOT NULL
         AND d.status IN ('pending', 'resolved', 'needs_review')`,
      [inventoryId],
    );
    const preserved = new Map<string, OfflineRecognitionProfileRow>();
    for (const row of rows) {
      if (!row.recognition_profile_snapshot_json) continue;
      try {
        const snapshot = JSON.parse(row.recognition_profile_snapshot_json) as {
          client_supplier_id?: string | null;
          item?: { profile_id?: string; profile_version?: number; profile_source?: string };
          position?: { profile_id?: string; profile_version?: number; profile_source?: string };
        };
        const supplierId = snapshot.client_supplier_id;
        if (!supplierId) continue;
        for (const kind of ['ITEM', 'POSITION'] as const) {
          const branch = kind === 'ITEM' ? snapshot.item : snapshot.position;
          if (!branch?.profile_id || branch.profile_version == null) continue;
          const key = profileKey(inventoryId, supplierId, kind);
          if (preserved.has(key)) continue;
          const existing = await this.getProfile(inventoryId, supplierId, kind);
          if (
            existing &&
            existing.profile_id === branch.profile_id &&
            existing.profile_version === branch.profile_version
          ) {
            preserved.set(key, existing);
          }
        }
      } catch {
        // ignore malformed snapshots
      }
    }
    return preserved;
  }
}

function profileKey(inventoryId: string, clientSupplierId: string, labelKind: string): string {
  return `${inventoryId}:${clientSupplierId}:${labelKind}`;
}
