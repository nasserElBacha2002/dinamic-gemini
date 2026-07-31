import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import type {
  AisleLocation,
  AisleLocationLabel,
  AisleLocationLabelListResponse,
  AisleLocationListResponse,
  CreateAisleLocationRequest,
  InvalidateAisleLocationLabelRequest,
  IssueAisleLocationLabelRequest,
  UpdateAisleLocationRequest,
} from './types';
import { buildQueryString } from './queryString';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface AisleLocationsListQuery {
  status?: string | null;
  search?: string | null;
  page?: number;
  page_size?: number;
}

function aisleLocationsBase(inventoryId: string, aisleId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/locations`;
}

function inventoryLocationLabelsBase(inventoryId: string, locationId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/locations/${encodeURIComponent(locationId)}/labels`;
}

export async function listAisleLocations(
  inventoryId: string,
  aisleId: string,
  listQuery?: AisleLocationsListQuery
): Promise<AisleLocationListResponse> {
  const qs = buildQueryString([
    ['status', listQuery?.status],
    ['search', listQuery?.search],
    ['page', listQuery?.page, { min: 1 }],
    ['page_size', listQuery?.page_size, { min: 1 }],
  ]);
  return apiRequestJson<AisleLocationListResponse>(`${aisleLocationsBase(inventoryId, aisleId)}${qs}`);
}

export async function createAisleLocation(
  inventoryId: string,
  aisleId: string,
  body: CreateAisleLocationRequest
): Promise<AisleLocation> {
  return apiRequestJson<AisleLocation>(aisleLocationsBase(inventoryId, aisleId), {
    method: 'POST',
    body,
  });
}

export async function updateAisleLocation(
  inventoryId: string,
  aisleId: string,
  locationId: string,
  body: UpdateAisleLocationRequest
): Promise<AisleLocation> {
  return apiRequestJson<AisleLocation>(
    `${aisleLocationsBase(inventoryId, aisleId)}/${encodeURIComponent(locationId)}`,
    {
      method: 'PATCH',
      body,
    }
  );
}

export async function listAisleLocationLabels(
  inventoryId: string,
  locationId: string,
  options?: { status?: string | null }
): Promise<AisleLocationLabelListResponse> {
  const qs = buildQueryString([['status', options?.status]]);
  return apiRequestJson<AisleLocationLabelListResponse>(
    `${inventoryLocationLabelsBase(inventoryId, locationId)}${qs}`
  );
}

export async function issueAisleLocationLabel(
  inventoryId: string,
  locationId: string,
  body?: IssueAisleLocationLabelRequest
): Promise<AisleLocationLabel> {
  return apiRequestJson<AisleLocationLabel>(inventoryLocationLabelsBase(inventoryId, locationId), {
    method: 'POST',
    body: body ?? {},
  });
}

export async function invalidateAisleLocationLabel(
  inventoryId: string,
  locationId: string,
  labelId: string,
  body?: InvalidateAisleLocationLabelRequest
): Promise<AisleLocationLabel> {
  return apiRequestJson<AisleLocationLabel>(
    `${inventoryLocationLabelsBase(inventoryId, locationId)}/${encodeURIComponent(labelId)}/invalidate`,
    {
      method: 'POST',
      body: body ?? {},
    }
  );
}
