import type { ApiClient } from '../../services/api/apiClient';
import type { AisleDto, AisleJobSummaryDto, PageDto } from '../../services/api/types';
import {
  aisleBlockReasonLabel,
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

  canSelect(aisle: AisleDto, local?: LocalCaptureHint): boolean {
    return this.evaluate(aisle, local).selectable;
  }

  evaluate(aisle: AisleDto, local?: LocalCaptureHint): AisleSelectionResult {
    const result = evaluateAisleSelection(aisle, local);
    if (!result.selectable && result.reason) {
      this.logger?.info('aisle_blocked', {
        aisleId: aisle.id,
        code: aisle.code,
        reason: result.reason,
        status: aisle.status,
        is_active: aisle.is_active,
        latestJob: aisle.latest_job?.status ?? null,
      });
    }
    return result;
  }

  blockLabel(result: AisleSelectionResult): string {
    return aisleBlockReasonLabel(result.reason);
  }
}

export interface SelectionDecision {
  readonly ok: boolean;
  readonly reason: string | null;
}

/** @deprecated Prefer evaluateAisleSelection — kept for existing tests. */
export function canSelectAisle(aisle: AisleDto, local?: LocalCaptureHint): SelectionDecision {
  const result = evaluateAisleSelection(aisle, local);
  return {
    ok: result.selectable,
    reason: result.selectable ? null : aisleBlockReasonLabel(result.reason) || 'No disponible',
  };
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

export { evaluateAisleSelection, aisleBlockReasonLabel } from '../../core/aisleSelection';
