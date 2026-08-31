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
    await this.db.withTransactionAsync(async () => {
      await this.db.runAsync(
        `DELETE FROM offline_recognition_profiles WHERE inventory_id = ?`,
        [bundle.inventory_id],
      );
      await this.db.runAsync(
        `DELETE FROM offline_aisle_recognition_config WHERE inventory_id = ?`,
        [bundle.inventory_id],
      );

      for (const aisle of bundle.aisles) {
        await this.insertAisle(bundle.inventory_id, aisle, syncedAtIso);
      }
      for (const profile of bundle.profiles) {
        await this.insertProfile(bundle.inventory_id, profile, syncedAtIso);
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

  private async insertProfile(
    inventoryId: string,
    profile: OfflineRecognitionProfileDto,
    syncedAt: string,
  ): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO offline_recognition_profiles (
         inventory_id, client_supplier_id, label_kind, source,
         profile_id, profile_version, configuration_schema_version,
         recognition_mode, semantic_type, configuration_json, synced_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        inventoryId,
        profile.client_supplier_id,
        profile.label_kind,
        profile.source,
        profile.profile_id,
        profile.profile_version,
        profile.configuration_schema_version,
        profile.recognition_mode ?? null,
        profile.semantic_type ?? null,
        JSON.stringify(profile.configuration ?? {}),
        syncedAt,
      ],
    );
  }
}
