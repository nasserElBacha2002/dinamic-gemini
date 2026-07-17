import type { ApiClient } from '../../services/api/apiClient';
import { ApiError } from '../../services/api/apiClient';
import type { AisleDto, AisleJobSummaryDto, CreateAisleRequestDto, PageDto } from '../../services/api/types';
import {
  evaluateAisleSelection,
  normalizeIsActive,
  normalizeStatus,
  type AisleSelectionResult,
  type LocalCaptureHint,
} from '../../core/aisleSelection';
import type { Logger } from '../../core/logging';

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
  constructor(
    private readonly api: ApiClient,
    private readonly logger?: Logger,
  ) {}

  async list(query: AisleQuery): Promise<PageDto<AisleDto>> {
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

  /** Always true — aisle selection is never blocked. */
  canSelect(_aisle?: AisleDto, _local?: LocalCaptureHint): boolean {
    return true;
  }

  evaluate(aisle: AisleDto, local?: LocalCaptureHint): AisleSelectionResult {
    return evaluateAisleSelection(aisle, local);
  }

  async create(input: CreateAisleInput): Promise<AisleDto> {
    const code = input.code.trim();
    if (!code) {
      throw new Error('El código del pasillo es obligatorio.');
    }
    if (code.length > 64) {
      throw new Error('El código del pasillo supera el máximo permitido (64).');
    }
    const supplierId = input.clientSupplierId?.trim();
    const body: CreateAisleRequestDto = supplierId
      ? { code, client_supplier_id: supplierId }
      : { code };
    try {
      const raw = await this.api.post<unknown>(
        `/api/v3/inventories/${encodeURIComponent(input.inventoryId)}/aisles`,
        body,
      );
      const created = normalizeAisleDto(raw);
      try {
        return await this.getById(input.inventoryId, created.id);
      } catch {
        return created;
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

  async getById(inventoryId: string, aisleId: string): Promise<AisleDto> {
    const status = await this.api.get<{ aisle: unknown }>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/status`,
    );
    return normalizeAisleDto(status.aisle);
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
  };
}

export { evaluateAisleSelection } from '../../core/aisleSelection';
