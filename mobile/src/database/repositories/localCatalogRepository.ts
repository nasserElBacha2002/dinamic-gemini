import type { SQLiteDatabase, SQLiteBindValue } from 'expo-sqlite';

import type {
  AisleDto,
  ClientSupplierDto,
  InventoryListItemDto,
  PageDto,
} from '../../services/api/types';
import { normalizeAisleDto } from '../../features/aisles/aisleService';
import type {
  LocalAisleOrigin,
  LocalAisleSyncStatus,
} from '../../features/aisles/localAisleTypes';
import type { CatalogRevisionInput } from '../../features/catalog/catalogRevision';
import {
  CATALOG_PROJECTION_VERSION,
  computeCatalogRevision,
} from '../../features/catalog/catalogRevision';

export interface LocalInventoryRow {
  id: string;
  client_id: string | null;
  name: string;
  status: string;
  active: number;
  processing_mode: string;
  aisles_count: number;
  pending_review_count: number;
  last_activity_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  server_updated_at: string | null;
  synced_at: string;
}

export interface LocalAisleRow {
  id: string;
  inventory_id: string;
  code: string;
  status: string;
  active: number;
  assets_count: number;
  positions_count: number;
  pending_review_positions_count: number;
  client_supplier_id: string | null;
  origin: LocalAisleOrigin;
  sync_status: LocalAisleSyncStatus;
  created_offline_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  server_updated_at: string | null;
  synced_at: string;
}

export interface InsertLocalAisleInput {
  readonly id: string;
  readonly inventoryId: string;
  readonly code: string;
  readonly clientSupplierId: string | null;
  readonly createdAtIso: string;
}

export interface LocalClientSupplierRow {
  id: string;
  client_id: string;
  name: string;
  status: string;
  active: number;
  created_at: string | null;
  updated_at: string | null;
  server_updated_at: string | null;
  synced_at: string;
}

export interface CatalogSyncMetaRow {
  id: number;
  catalog_revision: string | null;
  last_synced_at: string;
  inventory_count: number;
  supplier_count: number;
  aisle_count: number;
  last_sync_attempt_at: string | null;
  last_successful_sync_at: string | null;
  last_sync_status: string | null;
  catalog_projection_version: number;
}

export interface CatalogSnapshot {
  readonly inventories: readonly InventoryListItemDto[];
  readonly aisles: readonly AisleDto[];
  readonly suppliers: readonly ClientSupplierDto[];
  readonly revision: string;
}

export interface InventoryListQuery {
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
  readonly activeOnly?: boolean;
}

export interface AisleListQuery {
  readonly inventoryId: string;
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
  readonly activeOnly?: boolean;
}

export interface SupplierListQuery {
  readonly clientId: string;
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
  readonly activeOnly?: boolean;
}

export class LocalCatalogRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async getSyncMeta(): Promise<CatalogSyncMetaRow | null> {
    const row = await this.db.getFirstAsync<CatalogSyncMetaRow>(
      `SELECT id, catalog_revision, last_synced_at, inventory_count, supplier_count, aisle_count,
              last_sync_attempt_at, last_successful_sync_at, last_sync_status,
              catalog_projection_version
       FROM catalog_sync_meta WHERE id = 1`,
    );
    return row ?? null;
  }

  async recordSyncAttempt(attemptAtIso: string): Promise<void> {
    await this.db.runAsync(
      `INSERT INTO catalog_sync_meta
        (id, catalog_revision, last_synced_at, inventory_count, supplier_count, aisle_count, last_sync_attempt_at)
       VALUES (1, NULL, ?, 0, 0, 0, ?)
       ON CONFLICT(id) DO UPDATE SET last_sync_attempt_at = excluded.last_sync_attempt_at`,
      [attemptAtIso, attemptAtIso],
    );
  }

  async recordSyncResult(input: {
    readonly status: string;
    readonly attemptAtIso: string;
    readonly successfulAtIso: string | null;
  }): Promise<void> {
    await this.db.runAsync(
      `UPDATE catalog_sync_meta SET
         last_sync_attempt_at = ?,
         last_successful_sync_at = CASE
           WHEN ? IS NOT NULL THEN ?
           ELSE last_successful_sync_at
         END,
         last_sync_status = ?
       WHERE id = 1`,
      [input.attemptAtIso, input.successfulAtIso, input.successfulAtIso, input.status],
    );
  }

  async getInventoryById(inventoryId: string): Promise<LocalInventoryRow | null> {
    const row = await this.db.getFirstAsync<LocalInventoryRow>(
      `SELECT * FROM local_inventories WHERE id = ?`,
      [inventoryId],
    );
    return row ?? null;
  }

  async getAisleById(inventoryId: string, aisleId: string): Promise<LocalAisleRow | null> {
    const row = await this.db.getFirstAsync<LocalAisleRow>(
      `SELECT * FROM local_aisles WHERE inventory_id = ? AND id = ?`,
      [inventoryId, aisleId],
    );
    return row ?? null;
  }

  async getSupplierById(clientId: string, supplierId: string): Promise<LocalClientSupplierRow | null> {
    const row = await this.db.getFirstAsync<LocalClientSupplierRow>(
      `SELECT * FROM local_client_suppliers WHERE client_id = ? AND id = ?`,
      [clientId, supplierId],
    );
    return row ?? null;
  }

  /**
   * Persist a LOCAL_ONLY aisle atomically. Does not touch remote catalog sync meta.
   */
  async insertLocalAisle(input: InsertLocalAisleInput): Promise<LocalAisleRow> {
    await this.db.withTransactionAsync(async () => {
      await this.db.runAsync(
        `INSERT INTO local_aisles (
           id, inventory_id, code, status, active,
           assets_count, positions_count, pending_review_positions_count,
           client_supplier_id, origin, sync_status, created_offline_at,
           created_at, updated_at, server_updated_at, synced_at
         ) VALUES (?, ?, ?, 'created', 1, 0, 0, 0, ?, 'LOCAL', 'LOCAL_ONLY', ?, ?, ?, NULL, ?)`,
        [
          input.id,
          input.inventoryId,
          input.code,
          input.clientSupplierId,
          input.createdAtIso,
          input.createdAtIso,
          input.createdAtIso,
          input.createdAtIso,
        ],
      );
    });
    const row = await this.getAisleById(input.inventoryId, input.id);
    if (!row) {
      throw new Error('LOCAL_AISLE_CREATE_FAILED');
    }
    return row;
  }

  async countActiveInventories(): Promise<number> {
    const row = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM local_inventories WHERE active = 1`,
    );
    return row?.count ?? 0;
  }

  async countActiveSuppliers(): Promise<number> {
    const row = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM local_client_suppliers WHERE active = 1`,
    );
    return row?.count ?? 0;
  }

  async countProfiles(): Promise<number> {
    const row = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM offline_recognition_profiles`,
    );
    return row?.count ?? 0;
  }

  async listInventories(query: InventoryListQuery = {}): Promise<PageDto<InventoryListItemDto>> {
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 25);
    const offset = (page - 1) * pageSize;
    const where: string[] = [];
    const params: SQLiteBindValue[] = [];
    if (query.activeOnly !== false) {
      where.push('active = 1');
    }
    if (query.search?.trim()) {
      where.push('name LIKE ?');
      params.push(`%${query.search.trim()}%`);
    }
    const whereSql = where.length ? `WHERE ${where.join(' AND ')}` : '';
    const countRow = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM local_inventories ${whereSql}`,
      params,
    );
    const totalItems = countRow?.count ?? 0;
    const pageParams: SQLiteBindValue[] = [...params, pageSize, offset];
    const rows = await this.db.getAllAsync<LocalInventoryRow>(
      `SELECT * FROM local_inventories ${whereSql}
       ORDER BY COALESCE(last_activity_at, updated_at, created_at) DESC, name ASC
       LIMIT ? OFFSET ?`,
      pageParams,
    );
    return paginate(rows.map(mapInventoryRow), page, pageSize, totalItems);
  }

  async listAisles(query: AisleListQuery): Promise<PageDto<AisleDto>> {
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 50);
    const offset = (page - 1) * pageSize;
    const where: string[] = ['inventory_id = ?'];
    const params: SQLiteBindValue[] = [query.inventoryId];
    if (query.activeOnly !== false) {
      where.push('active = 1');
    }
    if (query.search?.trim()) {
      where.push('code LIKE ?');
      params.push(`%${query.search.trim()}%`);
    }
    const whereSql = `WHERE ${where.join(' AND ')}`;
    const countRow = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM local_aisles ${whereSql}`,
      params,
    );
    const totalItems = countRow?.count ?? 0;
    const pageParams: SQLiteBindValue[] = [...params, pageSize, offset];
    const rows = await this.db.getAllAsync<LocalAisleRow>(
      `SELECT * FROM local_aisles ${whereSql}
       ORDER BY code ASC
       LIMIT ? OFFSET ?`,
      pageParams,
    );
    return paginate(rows.map(mapAisleRow), page, pageSize, totalItems);
  }

  async listSuppliers(query: SupplierListQuery): Promise<PageDto<ClientSupplierDto>> {
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 200);
    const offset = (page - 1) * pageSize;
    const where: string[] = ['client_id = ?'];
    const params: SQLiteBindValue[] = [query.clientId];
    if (query.activeOnly !== false) {
      where.push('active = 1');
    }
    if (query.search?.trim()) {
      where.push('name LIKE ?');
      params.push(`%${query.search.trim()}%`);
    }
    const whereSql = `WHERE ${where.join(' AND ')}`;
    const countRow = await this.db.getFirstAsync<{ count: number }>(
      `SELECT COUNT(*) AS count FROM local_client_suppliers ${whereSql}`,
      params,
    );
    const totalItems = countRow?.count ?? 0;
    const pageParams: SQLiteBindValue[] = [...params, pageSize, offset];
    const rows = await this.db.getAllAsync<LocalClientSupplierRow>(
      `SELECT * FROM local_client_suppliers ${whereSql}
       ORDER BY name ASC
       LIMIT ? OFFSET ?`,
      pageParams,
    );
    return paginate(rows.map(mapSupplierRow), page, pageSize, totalItems);
  }

  /**
   * Atomic catalog replace. On failure the previous committed state remains.
   */
  async replaceCatalogSnapshot(snapshot: CatalogSnapshot, syncedAtIso: string): Promise<void> {
    const revisionInput: CatalogRevisionInput = {
      inventories: snapshot.inventories.map((inv) => ({
        id: inv.id,
        client_id: inv.client_id,
        name: inv.name,
        status: inv.status,
        updated_at: inv.updated_at,
        processing_mode: inv.processing_mode,
      })),
      aisles: snapshot.aisles.map((aisle) => ({
        id: aisle.id,
        inventory_id: aisle.inventory_id,
        code: aisle.code,
        status: aisle.status,
        updated_at: aisle.updated_at,
        is_active: aisle.is_active ?? true,
        client_supplier_id: aisle.client_supplier_id ?? null,
      })),
      suppliers: snapshot.suppliers.map((supplier) => ({
        id: supplier.id,
        client_id: supplier.client_id,
        name: supplier.name,
        status: supplier.status,
        updated_at: supplier.updated_at,
      })),
    };
    const revision = snapshot.revision || computeCatalogRevision(revisionInput);

    await this.db.withTransactionAsync(async () => {
      await this.db.runAsync(`UPDATE local_inventories SET active = 0 WHERE active = 1`);
      for (const inv of snapshot.inventories) {
        await this.db.runAsync(
          `INSERT INTO local_inventories (
             id, client_id, name, status, active, processing_mode,
             aisles_count, pending_review_count, last_activity_at,
             created_at, updated_at, server_updated_at, synced_at
           ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             client_id = excluded.client_id,
             name = excluded.name,
             status = excluded.status,
             active = 1,
             processing_mode = excluded.processing_mode,
             aisles_count = excluded.aisles_count,
             pending_review_count = excluded.pending_review_count,
             last_activity_at = excluded.last_activity_at,
             created_at = excluded.created_at,
             updated_at = excluded.updated_at,
             server_updated_at = excluded.server_updated_at,
             synced_at = excluded.synced_at`,
          [
            inv.id,
            inv.client_id,
            inv.name,
            inv.status,
            inv.processing_mode,
            inv.aisles_count,
            inv.pending_review_count,
            inv.last_activity_at,
            inv.created_at,
            inv.updated_at,
            inv.updated_at,
            syncedAtIso,
          ],
        );
      }

      await this.db.runAsync(
        `UPDATE local_aisles SET active = 0 WHERE active = 1 AND (origin IS NULL OR origin = 'REMOTE')`,
      );
      for (const aisle of snapshot.aisles) {
        await this.db.runAsync(
          `INSERT INTO local_aisles (
             id, inventory_id, code, status, active,
             assets_count, positions_count, pending_review_positions_count,
             client_supplier_id, origin, sync_status, created_offline_at,
             created_at, updated_at, server_updated_at, synced_at
           ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'REMOTE', 'REMOTE_SYNCED', NULL, ?, ?, ?, ?)
           ON CONFLICT(inventory_id, id) DO UPDATE SET
             code = excluded.code,
             status = excluded.status,
             active = 1,
             assets_count = excluded.assets_count,
             positions_count = excluded.positions_count,
             pending_review_positions_count = excluded.pending_review_positions_count,
             client_supplier_id = excluded.client_supplier_id,
             origin = 'REMOTE',
             sync_status = 'REMOTE_SYNCED',
             created_at = excluded.created_at,
             updated_at = excluded.updated_at,
             server_updated_at = excluded.server_updated_at,
             synced_at = excluded.synced_at`,
          [
            aisle.id,
            aisle.inventory_id,
            aisle.code,
            aisle.status,
            aisle.assets_count,
            aisle.positions_count,
            aisle.pending_review_positions_count,
            aisle.client_supplier_id ?? null,
            aisle.created_at,
            aisle.updated_at,
            aisle.updated_at,
            syncedAtIso,
          ],
        );
      }

      await this.db.runAsync(`UPDATE local_client_suppliers SET active = 0 WHERE active = 1`);
      for (const supplier of snapshot.suppliers) {
        await this.db.runAsync(
          `INSERT INTO local_client_suppliers (
             id, client_id, name, status, active,
             created_at, updated_at, server_updated_at, synced_at
           ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
           ON CONFLICT(client_id, id) DO UPDATE SET
             name = excluded.name,
             status = excluded.status,
             active = 1,
             created_at = excluded.created_at,
             updated_at = excluded.updated_at,
             server_updated_at = excluded.server_updated_at,
             synced_at = excluded.synced_at`,
          [
            supplier.id,
            supplier.client_id,
            supplier.name,
            supplier.status,
            supplier.created_at,
            supplier.updated_at,
            supplier.updated_at,
            syncedAtIso,
          ],
        );
      }

      await this.db.runAsync(
        `INSERT INTO catalog_sync_meta
          (id, catalog_revision, last_synced_at, inventory_count, supplier_count, aisle_count,
           last_sync_attempt_at, last_successful_sync_at, last_sync_status,
           catalog_projection_version)
         VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?)
         ON CONFLICT(id) DO UPDATE SET
           catalog_revision = excluded.catalog_revision,
           last_synced_at = excluded.last_synced_at,
           inventory_count = excluded.inventory_count,
           supplier_count = excluded.supplier_count,
           aisle_count = excluded.aisle_count,
           last_successful_sync_at = excluded.last_successful_sync_at,
           last_sync_status = excluded.last_sync_status,
           catalog_projection_version = excluded.catalog_projection_version`,
        [
          revision,
          syncedAtIso,
          snapshot.inventories.length,
          snapshot.suppliers.length,
          snapshot.aisles.length,
          syncedAtIso,
          syncedAtIso,
          CATALOG_PROJECTION_VERSION,
        ],
      );
    });
  }
}

function mapInventoryRow(row: LocalInventoryRow): InventoryListItemDto {
  return {
    id: row.id,
    name: row.name,
    status: row.status,
    client_id: row.client_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    aisles_count: row.aisles_count,
    pending_review_count: row.pending_review_count,
    last_activity_at: row.last_activity_at,
    processing_mode: row.processing_mode,
  };
}

function mapAisleRow(row: LocalAisleRow): AisleDto {
  return normalizeAisleDto({
    id: row.id,
    inventory_id: row.inventory_id,
    code: row.code,
    status: row.status,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
    is_active: row.active === 1,
    assets_count: row.assets_count,
    positions_count: row.positions_count,
    pending_review_positions_count: row.pending_review_positions_count,
    origin: row.origin ?? 'REMOTE',
    sync_status: row.sync_status ?? 'REMOTE_SYNCED',
    client_supplier_id: row.client_supplier_id,
    created_offline_at: row.created_offline_at,
  });
}

function mapSupplierRow(row: LocalClientSupplierRow): ClientSupplierDto {
  return {
    id: row.id,
    client_id: row.client_id,
    name: row.name,
    status: row.status,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
}

function paginate<T>(
  items: readonly T[],
  page: number,
  pageSize: number,
  totalItems: number,
): PageDto<T> {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  return {
    items: [...items],
    page,
    page_size: pageSize,
    total_items: totalItems,
    total_pages: totalPages,
  };
}
