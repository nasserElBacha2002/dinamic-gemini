import type { AisleListQuery, LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
import type { OfflineRecognitionConfigRepository } from '../../database/repositories/offlineRecognitionConfigRepository';
import type { ApiClient } from '../../services/api/apiClient';
import { ApiError, NETWORK_ERROR, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import type { AisleDto, AisleJobSummaryDto, CreateAisleRequestDto, PageDto } from '../../services/api/types';
import {
  evaluateAisleSelection,
  normalizeIsActive,
  normalizeStatus,
  type AisleSelectionResult,
  type LocalCaptureHint,
} from '../../core/aisleSelection';
import type { Logger } from '../../core/logging';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { CatalogSyncCoordinator } from '../catalog/catalogSyncCoordinator';
import { canUseSupplierOffline } from './canUseSupplierOffline';
import { getAisleCreationRules } from './aisleCreationRules';
import { LocalAisleError } from './localAisleErrors';
import { validateAisleCode } from './validateAisleCode';
import { createId } from '../../shared/createId';
import type { ObservabilityReporter } from '../../observability/types';
import { emitObservability } from '../../observability/emitHelpers';
import type { LocalLabelProfileResolver } from '../offlineRecognition/localLabelProfileResolver';

export interface AisleQuery {
  readonly inventoryId: string;
  readonly search?: string;
  readonly page?: number;
  readonly pageSize?: number;
}

export interface CreateAisleInput {
  readonly inventoryId: string;
  readonly code: string;
  readonly clientSupplierId?: string | null;
}

export class AisleService {
  private localCreateInFlight = false;
  private readonly pendingRemoteMaterialization = new Map<string, AisleDto>();

  constructor(
    private readonly api: ApiClient,
    private readonly logger?: Logger,
    private readonly catalog?: LocalCatalogRepository,
    private readonly catalogSync?: CatalogSyncCoordinator,
    private readonly connectivity?: ConnectivityService,
    private readonly recognitionRepo?: OfflineRecognitionConfigRepository,
    private readonly observability?: ObservabilityReporter | null,
    private readonly recognitionResolver?: LocalLabelProfileResolver,
  ) {}

  async listLocal(query: AisleQuery): Promise<PageDto<AisleDto>> {
    if (!this.catalog) {
      return emptyPage(query);
    }
    return this.catalog.listAisles(buildAisleListQuery(query));
  }

  async list(query: AisleQuery): Promise<PageDto<AisleDto>> {
    const local = await this.listLocal(query);
    if (local.total_items > 0 || this.connectivity?.getState() === 'offline') {
      if (this.connectivity?.getState() !== 'offline') {
        void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      }
      return local;
    }
    try {
      const remote = await this.fetchRemoteList(query);
      void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      return remote;
    } catch (e) {
      if (shouldFallbackToLocal(e) && local.total_items > 0) {
        return local;
      }
      throw e;
    }
  }

  /** Always true — aisle selection is never blocked. */
  canSelect(_aisle?: AisleDto, _local?: LocalCaptureHint): boolean {
    return true;
  }

  evaluate(aisle: AisleDto, local?: LocalCaptureHint): AisleSelectionResult {
    return evaluateAisleSelection(aisle, local);
  }

  async create(input: CreateAisleInput): Promise<AisleDto> {
    const code = validateAisleCode(input.code);
    const supplierId = input.clientSupplierId?.trim();
    const pendingKey = `${input.inventoryId}:${code}`;
    const pending = this.pendingRemoteMaterialization.get(pendingKey);
    if (pending) {
      const materialized = await this.materializeCreatedRemoteAisle(input.inventoryId, pending);
      this.pendingRemoteMaterialization.delete(pendingKey);
      return materialized;
    }
    const body: CreateAisleRequestDto = supplierId
      ? { code, client_supplier_id: supplierId }
      : { code };
    try {
      const raw = await this.api.post<unknown>(
        `/api/v3/inventories/${encodeURIComponent(input.inventoryId)}/aisles`,
        body,
      );
      const created = normalizeAisleDto(raw);
      let authoritative = created;
      try {
        authoritative = await this.getById(input.inventoryId, created.id);
      } catch {
        // The POST representation is authoritative enough when status refresh is unavailable.
      }
      if (supplierId && authoritative.client_supplier_id !== supplierId) {
        this.reportRemoteMaterializationFailure(
          input.inventoryId,
          authoritative,
          'REMOTE_AISLE_SUPPLIER_ASSOCIATION_MISSING',
        );
        throw new LocalAisleError('REMOTE_AISLE_MATERIALIZATION_FAILED');
      }
      try {
        const materialized = await this.materializeCreatedRemoteAisle(input.inventoryId, authoritative);
        this.pendingRemoteMaterialization.delete(pendingKey);
        return materialized;
      } catch (e) {
        // The backend creation already succeeded. Keep its response in memory so a UI retry
        // retries only the local projection/readiness gate, never a blind duplicate POST.
        this.pendingRemoteMaterialization.set(pendingKey, authoritative);
        throw e;
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        throw new Error('No tenés permisos para realizar esta acción.');
      }
      if (e instanceof ApiError && e.status === 409) {
        throw new Error(e.message || 'Ya existe un pasillo con ese código.');
      }
      throw e;
    }
  }

  private async materializeCreatedRemoteAisle(
    inventoryId: string,
    aisle: AisleDto,
  ): Promise<AisleDto> {
    if (!this.catalog || !aisle.id || !aisle.inventory_id || aisle.inventory_id !== inventoryId) {
      this.reportRemoteMaterializationFailure(inventoryId, aisle, 'INVALID_REMOTE_AISLE');
      throw new LocalAisleError('REMOTE_AISLE_MATERIALIZATION_FAILED');
    }

    try {
      const row = await this.catalog.upsertRemoteAisle(aisle, new Date().toISOString());
      this.recognitionResolver?.invalidate();
      if (this.recognitionResolver) {
        const resolved = await this.recognitionResolver.resolveForAisle(inventoryId, aisle.id);
        const notReady = [resolved.item, resolved.position].some(
          (profile) => profile.missingSupplierProfile || profile.recognitionConfigNotReady,
        );
        if (notReady) {
          throw new LocalAisleError('RECOGNITION_CONFIG_NOT_READY');
        }
      }
      emitObservability(this.observability, {
        name: 'mobile.aisle.remote_materialized',
        attributes: {
          aisle_id: aisle.id,
          inventory_id: inventoryId,
          supplier_id: row.client_supplier_id,
          client_supplier_id: row.client_supplier_id,
          origin: 'REMOTE',
          offline: false,
        },
      });
      this.logger?.info('recovery', {
        obs_name: 'remote_aisle_materialized',
        aisleId: aisle.id,
        inventoryId,
        supplierId: row.client_supplier_id,
      });
      return normalizeAisleDto(row);
    } catch (e) {
      this.reportRemoteMaterializationFailure(
        inventoryId,
        aisle,
        e instanceof LocalAisleError ? e.code : 'REMOTE_AISLE_MATERIALIZATION_FAILED',
      );
      if (e instanceof LocalAisleError) throw e;
      throw new LocalAisleError('REMOTE_AISLE_MATERIALIZATION_FAILED');
    }
  }

  private reportRemoteMaterializationFailure(
    inventoryId: string,
    aisle: AisleDto,
    errorCode: string,
  ): void {
    emitObservability(this.observability, {
      name: 'mobile.aisle.remote_materialization_failed',
      attributes: {
        aisle_id: aisle.id || null,
        inventory_id: inventoryId,
        supplier_id: aisle.client_supplier_id ?? null,
        client_supplier_id: aisle.client_supplier_id ?? null,
        origin: 'REMOTE',
        offline: false,
        error_code: errorCode,
      },
    });
    this.logger?.warn('recovery', {
      obs_name: 'remote_aisle_materialization_failed',
      aisleId: aisle.id || null,
      inventoryId,
      errorCode,
    });
  }

  /**
   * Create a LOCAL_ONLY aisle in SQLite without backend calls.
   */
  async createLocal(input: CreateAisleInput): Promise<AisleDto> {
    if (this.localCreateInFlight) {
      throw new LocalAisleError('LOCAL_AISLE_CREATE_FAILED', 'Creación de pasillo en curso.');
    }
    if (!this.catalog) {
      throw new LocalAisleError('LOCAL_AISLE_CREATE_FAILED');
    }

    const code = validateAisleCode(input.code);
    const inventoryId = input.inventoryId;
    const aisleId = createId();
    const nowIso = new Date().toISOString();

    this.localCreateInFlight = true;
    emitObservability(this.observability, {
      name: 'mobile.aisle.local_create_started',
      attributes: {
        aisle_id: aisleId,
        inventory_id: inventoryId,
        supplier_id: input.clientSupplierId ?? null,
        offline: true,
      },
    });

    try {
      const inventory = await this.catalog.getInventoryById(inventoryId);
      if (!inventory || inventory.active !== 1) {
        throw new LocalAisleError(
          inventory ? 'INVENTORY_INACTIVE' : 'INVENTORY_NOT_AVAILABLE_OFFLINE',
        );
      }

      const rules = getAisleCreationRules({ client_id: inventory.client_id });
      const supplierId = input.clientSupplierId?.trim() || null;
      if (rules.supplierRequired && !supplierId) {
        throw new LocalAisleError('SUPPLIER_NOT_AVAILABLE_OFFLINE', rules.reason);
      }

      if (supplierId && !inventory.client_id) {
        throw new LocalAisleError('INVENTORY_CLIENT_NOT_AVAILABLE_OFFLINE');
      }

      if (supplierId) {
        const supplier = await this.catalog.getSupplierById(inventory.client_id!, supplierId);
        if (!supplier) {
          throw new LocalAisleError('SUPPLIER_NOT_AVAILABLE_OFFLINE');
        }
        if (supplier.active !== 1) {
          throw new LocalAisleError('SUPPLIER_INACTIVE');
        }
        if (supplier.client_id !== inventory.client_id) {
          throw new LocalAisleError('SUPPLIER_CLIENT_MISMATCH');
        }

        if (!this.recognitionRepo) {
          throw new LocalAisleError('RECOGNITION_CONFIG_NOT_READY');
        }
        const readiness = await canUseSupplierOffline({
          inventoryId,
          inventoryClientId: inventory.client_id!,
          clientSupplierId: supplierId,
          catalog: this.catalog,
          recognitionRepo: this.recognitionRepo,
        });
        if (readiness.status !== 'READY_OFFLINE') {
          throw new LocalAisleError(
            'RECOGNITION_CONFIG_NOT_READY',
            readiness.message ?? undefined,
          );
        }
      }

      const row = await this.catalog.insertLocalAisle({
        id: aisleId,
        inventoryId,
        code,
        clientSupplierId: supplierId,
        createdAtIso: nowIso,
      });

      emitObservability(this.observability, {
        name: 'mobile.aisle.local_created',
        attributes: {
          aisle_id: aisleId,
          inventory_id: inventoryId,
          supplier_id: supplierId,
          offline: true,
        },
      });

      this.logger?.info('recovery', {
        obs_name: 'local_aisle_created',
        aisleId,
        inventoryId,
        supplierId,
      });

      return normalizeAisleDto({
        id: row.id,
        inventory_id: row.inventory_id,
        code: row.code,
        status: row.status,
        created_at: row.created_at ?? nowIso,
        updated_at: row.updated_at ?? nowIso,
        is_active: row.active === 1,
        assets_count: row.assets_count,
        positions_count: row.positions_count,
        pending_review_positions_count: row.pending_review_positions_count,
        origin: row.origin,
        sync_status: row.sync_status,
        client_supplier_id: row.client_supplier_id,
        created_offline_at: row.created_offline_at,
      });
    } catch (e) {
      emitObservability(this.observability, {
        name: 'mobile.aisle.local_create_failed',
        attributes: {
          aisle_id: aisleId,
          inventory_id: inventoryId,
          supplier_id: input.clientSupplierId ?? null,
          offline: true,
          error_code: e instanceof LocalAisleError ? e.code : 'LOCAL_AISLE_CREATE_FAILED',
        },
      });
      if (e instanceof LocalAisleError) {
        throw e;
      }
      throw new LocalAisleError('LOCAL_AISLE_CREATE_FAILED');
    } finally {
      this.localCreateInFlight = false;
    }
  }

  async getById(inventoryId: string, aisleId: string): Promise<AisleDto> {
    const local = await this.catalog?.getAisleById(inventoryId, aisleId);
    if (local && local.active === 1) {
      if (this.connectivity?.getState() !== 'offline') {
        void this.catalogSync?.requestSync('screen_refresh').catch(() => undefined);
      }
      return normalizeAisleDto({
        id: local.id,
        inventory_id: local.inventory_id,
        code: local.code,
        status: local.status,
        created_at: local.created_at ?? '',
        updated_at: local.updated_at ?? '',
        is_active: local.active === 1,
        assets_count: local.assets_count,
        positions_count: local.positions_count,
        pending_review_positions_count: local.pending_review_positions_count,
        origin: local.origin,
        sync_status: local.sync_status,
        client_supplier_id: local.client_supplier_id,
        created_offline_at: local.created_offline_at,
      });
    }
    if (this.connectivity?.getState() === 'offline') {
      throw new Error('Pasillo no disponible offline.');
    }
    const status = await this.api.get<{ aisle: unknown }>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/status`,
    );
    return normalizeAisleDto(status.aisle);
  }

  private async fetchRemoteList(query: AisleQuery): Promise<PageDto<AisleDto>> {
    const params = new URLSearchParams({
      page: String(query.page ?? 1),
      page_size: String(query.pageSize ?? 50),
      sort_by: 'code',
      sort_dir: 'asc',
    });
    if (query.search?.trim()) {
      params.set('search', query.search.trim());
    }
    const raw = await this.api.get<PageDto<unknown>>(
      `/api/v3/inventories/${encodeURIComponent(query.inventoryId)}/aisles?${params.toString()}`,
    );
    return {
      ...raw,
      items: (raw.items ?? []).map((item) => normalizeAisleDto(item)),
    };
  }
}

export interface SelectionDecision {
  readonly ok: boolean;
  readonly reason: string | null;
}

export function canSelectAisle(_aisle?: AisleDto, _local?: LocalCaptureHint): SelectionDecision {
  return { ok: true, reason: null };
}

export function normalizeAisleDto(raw: unknown): AisleDto {
  const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const latestRaw = o.latest_job ?? o.latestJob;
  let latest_job: AisleJobSummaryDto | null = null;
  if (latestRaw && typeof latestRaw === 'object') {
    const j = latestRaw as Record<string, unknown>;
    latest_job = {
      id: String(j.id ?? ''),
      status: String(j.status ?? ''),
      created_at: String(j.created_at ?? j.createdAt ?? ''),
      updated_at: String(j.updated_at ?? j.updatedAt ?? ''),
      error_message: (j.error_message ?? j.errorMessage ?? null) as string | null,
      failure_code: (j.failure_code ?? j.failureCode ?? null) as string | null,
      failure_message: (j.failure_message ?? j.failureMessage ?? null) as string | null,
    };
  }
  return {
    id: String(o.id ?? ''),
    inventory_id: String(o.inventory_id ?? o.inventoryId ?? ''),
    code: String(o.code ?? ''),
    status: normalizeStatus(o.status) || String(o.status ?? ''),
    created_at: String(o.created_at ?? o.createdAt ?? ''),
    updated_at: String(o.updated_at ?? o.updatedAt ?? ''),
    is_active: normalizeIsActive(o.is_active ?? o.isActive),
    error_code: (o.error_code ?? o.errorCode ?? null) as string | null,
    error_message: (o.error_message ?? o.errorMessage ?? null) as string | null,
    latest_job,
    assets_count: Number(o.assets_count ?? o.assetsCount ?? 0) || 0,
    positions_count: Number(o.positions_count ?? o.positionsCount ?? 0) || 0,
    pending_review_positions_count:
      Number(o.pending_review_positions_count ?? o.pendingReviewPositionsCount ?? 0) || 0,
    last_activity_at: (o.last_activity_at ?? o.lastActivityAt ?? null) as string | null,
    ...(pickOptionalAisleLocalFields(o)),
  };
}

function pickOptionalAisleLocalFields(o: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const origin = o.origin;
  if (origin === 'REMOTE' || origin === 'LOCAL') out.origin = origin;
  const syncStatus = o.sync_status ?? o.syncStatus;
  if (syncStatus === 'REMOTE_SYNCED' || syncStatus === 'LOCAL_ONLY') out.sync_status = syncStatus;
  if (o.client_supplier_id !== undefined || o.clientSupplierId !== undefined) {
    out.client_supplier_id = (o.client_supplier_id ?? o.clientSupplierId ?? null) as string | null;
  }
  if (o.created_offline_at !== undefined || o.createdOfflineAt !== undefined) {
    out.created_offline_at = (o.created_offline_at ?? o.createdOfflineAt ?? null) as string | null;
  }
  return out;
}

export { evaluateAisleSelection } from '../../core/aisleSelection';

function emptyPage(query: AisleQuery): PageDto<AisleDto> {
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 50;
  return {
    items: [],
    page,
    page_size: pageSize,
    total_items: 0,
    total_pages: 1,
  };
}

function shouldFallbackToLocal(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return true;
  }
  if (error.status === null) {
    return error.code === NETWORK_ERROR || error.code === REQUEST_TIMEOUT;
  }
  return error.status >= 500;
}

function buildAisleListQuery(query: AisleQuery): AisleListQuery {
  return {
    inventoryId: query.inventoryId,
    ...(query.search !== undefined ? { search: query.search } : {}),
    ...(query.page !== undefined ? { page: query.page } : {}),
    ...(query.pageSize !== undefined ? { pageSize: query.pageSize } : {}),
  };
}
