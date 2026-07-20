import {
  pathToClientSuppliersBase,
  supplierExtractionProfileActivatePath,
  supplierExtractionProfileByVersionPath,
  supplierExtractionProfilesActivePath,
  supplierExtractionProfilesClonePath,
  supplierExtractionProfilesPath,
  supplierPromptConfigActivatePath,
  supplierPromptConfigByIdPath,
  supplierPromptConfigsActivePath,
  supplierPromptConfigsPath,
  supplierReferenceImageAnnotationsPath,
  supplierReferenceImageDisplayUrlPath,
  supplierReferenceImageFilePath,
  supplierReferenceImagesPath,
  supplierReferenceImagePath,
  V3_CLIENTS_BASE,
} from '../constants/v3ApiPaths';
import type {
  ClientSupplier,
  ClientSuppliersListResponse,
  CreateSupplierPromptConfigRequest,
  CreateSupplierExtractionProfileRequest,
  CloneSupplierExtractionProfileRequest,
  ReplaceSupplierReferenceAnnotationsRequest,
  CreateClientSupplierRequest,
  DeleteSupplierReferenceImageResponse,
  SupplierPromptConfig,
  SupplierPromptConfigsListResponse,
  SupplierExtractionProfile,
  SupplierExtractionProfilesListResponse,
  SupplierReferenceAnnotationsListResponse,
  SupplierReferenceImagesListResponse,
  UploadSupplierReferenceImagesRequest,
  UploadSupplierReferenceImagesResponse,
} from './types';
import {
  fetchReferenceImageDisplay,
  type FetchReferenceImageDisplayResult,
} from '../utils/fetchReferenceImageDisplay';
import { buildQueryString } from './queryString';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientSuppliersListQuery {
  page?: number;
  page_size?: number;
}

function buildClientSuppliersListQueryString(q?: ClientSuppliersListQuery): string {
  return buildQueryString([
    ['page', q?.page, { min: 1 }],
    ['page_size', q?.page_size, { min: 1 }],
  ]);
}

export async function listClientSuppliers(
  clientId: string,
  listQuery?: ClientSuppliersListQuery
): Promise<ClientSuppliersListResponse> {
  const qs = buildClientSuppliersListQueryString(listQuery);
  return apiRequestJson<ClientSuppliersListResponse>(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}${qs}`
  );
}

export async function getClientSupplier(
  clientId: string,
  supplierId: string
): Promise<ClientSupplier> {
  return apiRequestJson<ClientSupplier>(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}`
  );
}

export async function createClientSupplier(
  clientId: string,
  body: CreateClientSupplierRequest
): Promise<ClientSupplier> {
  return apiRequestJson<ClientSupplier>(
    `${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/suppliers`,
    {
      method: 'POST',
      body,
    }
  );
}

export async function listSupplierReferenceImages(
  clientId: string,
  supplierId: string
): Promise<SupplierReferenceImagesListResponse> {
  return apiRequestJson<SupplierReferenceImagesListResponse>(
    `${API_BASE}${supplierReferenceImagesPath(clientId, supplierId)}`
  );
}

export async function uploadSupplierReferenceImages(
  clientId: string,
  supplierId: string,
  payload: UploadSupplierReferenceImagesRequest
): Promise<UploadSupplierReferenceImagesResponse> {
  const form = new FormData();
  payload.files.forEach((file) => form.append('files', file));
  const label = (payload.label ?? '').trim();
  const description = (payload.description ?? '').trim();
  if (label) form.append('label', label);
  if (description) form.append('description', description);
  return apiRequestJson<UploadSupplierReferenceImagesResponse>(
    `${API_BASE}${supplierReferenceImagesPath(clientId, supplierId)}`,
    { method: 'POST', body: form }
  );
}

export async function deleteSupplierReferenceImage(
  clientId: string,
  supplierId: string,
  imageId: string
): Promise<DeleteSupplierReferenceImageResponse> {
  return apiRequestJson<DeleteSupplierReferenceImageResponse>(
    `${API_BASE}${supplierReferenceImagePath(clientId, supplierId, imageId)}`,
    { method: 'DELETE' }
  );
}

/** Absolute URL for GET …/reference-images/{imageId}/file (Bearer not included — prefer fetchSupplierReferenceImageFile for preview). */
export function getSupplierReferenceImageFileUrl(
  clientId: string,
  supplierId: string,
  imageId: string
): string {
  return `${API_BASE}${supplierReferenceImageFilePath(clientId, supplierId, imageId)}`;
}

export function getSupplierReferenceImageDisplayUrl(
  clientId: string,
  supplierId: string,
  imageId: string
): string {
  return `${API_BASE}${supplierReferenceImageDisplayUrlPath(clientId, supplierId, imageId)}`;
}

export type FetchSupplierReferenceImageDisplayResult = FetchReferenceImageDisplayResult;

/** Resolve preview URL via image-display-url (presigned GCS/S3) or authenticated /file blob. */
export async function fetchSupplierReferenceImageDisplay(
  clientId: string,
  supplierId: string,
  imageId: string
): Promise<FetchSupplierReferenceImageDisplayResult> {
  return fetchReferenceImageDisplay(
    getSupplierReferenceImageDisplayUrl(clientId, supplierId, imageId),
    getSupplierReferenceImageFileUrl(clientId, supplierId, imageId)
  );
}

/** @deprecated Prefer fetchSupplierReferenceImageDisplay for preview (avoids CORS on GCS signed URLs). */
export async function fetchSupplierReferenceImageFile(
  clientId: string,
  supplierId: string,
  imageId: string
): Promise<{ imageSrc: string; revoke: () => void }> {
  const result = await fetchSupplierReferenceImageDisplay(clientId, supplierId, imageId);
  if (!result.ok) {
    throw new Error(result.detail ?? 'Preview failed');
  }
  return {
    imageSrc: result.imageSrc,
    revoke: result.revoke ?? (() => {}),
  };
}

export interface SupplierPromptConfigsListQuery {
  scope?: 'all';
  provider_name?: string | null;
  model_name?: string | null;
}

function buildSupplierPromptConfigsQueryString(q?: SupplierPromptConfigsListQuery): string {
  return buildQueryString([
    ['scope', q?.scope === 'all' ? 'all' : undefined],
    ['provider_name', q?.provider_name],
    ['model_name', q?.model_name],
  ]);
}

export async function listSupplierPromptConfigs(
  clientId: string,
  supplierId: string,
  listQuery?: SupplierPromptConfigsListQuery
): Promise<SupplierPromptConfigsListResponse> {
  const qs = buildSupplierPromptConfigsQueryString(listQuery);
  return apiRequestJson<SupplierPromptConfigsListResponse>(
    `${API_BASE}${supplierPromptConfigsPath(clientId, supplierId)}${qs}`
  );
}

export async function createSupplierPromptConfigVersion(
  clientId: string,
  supplierId: string,
  body: CreateSupplierPromptConfigRequest
): Promise<SupplierPromptConfig> {
  return apiRequestJson<SupplierPromptConfig>(
    `${API_BASE}${supplierPromptConfigsPath(clientId, supplierId)}`,
    {
      method: 'POST',
      body,
    }
  );
}

export async function getActiveSupplierPromptConfig(
  clientId: string,
  supplierId: string,
  providerName?: string | null,
  modelName?: string | null
): Promise<SupplierPromptConfig> {
  const qs = buildQueryString([
    ['provider_name', providerName ?? undefined],
    ['model_name', modelName ?? undefined],
  ]);
  const suffix = qs === '' ? '?' : qs;
  return apiRequestJson<SupplierPromptConfig>(
    `${API_BASE}${supplierPromptConfigsActivePath(clientId, supplierId)}${suffix}`
  );
}

export async function getSupplierPromptConfigById(
  clientId: string,
  supplierId: string,
  configId: string
): Promise<SupplierPromptConfig> {
  return apiRequestJson<SupplierPromptConfig>(
    `${API_BASE}${supplierPromptConfigByIdPath(clientId, supplierId, configId)}`
  );
}

export async function activateSupplierPromptConfigVersion(
  clientId: string,
  supplierId: string,
  configId: string
): Promise<SupplierPromptConfig> {
  return apiRequestJson<SupplierPromptConfig>(
    `${API_BASE}${supplierPromptConfigActivatePath(clientId, supplierId, configId)}`,
    { method: 'POST' }
  );
}

export async function listSupplierExtractionProfiles(
  clientId: string,
  supplierId: string
): Promise<SupplierExtractionProfilesListResponse> {
  return apiRequestJson<SupplierExtractionProfilesListResponse>(
    `${API_BASE}${supplierExtractionProfilesPath(clientId, supplierId)}`
  );
}

export async function getActiveSupplierExtractionProfile(
  clientId: string,
  supplierId: string
): Promise<SupplierExtractionProfile> {
  return apiRequestJson<SupplierExtractionProfile>(
    `${API_BASE}${supplierExtractionProfilesActivePath(clientId, supplierId)}`
  );
}

export async function getSupplierExtractionProfileByVersion(
  clientId: string,
  supplierId: string,
  version: number
): Promise<SupplierExtractionProfile> {
  return apiRequestJson<SupplierExtractionProfile>(
    `${API_BASE}${supplierExtractionProfileByVersionPath(clientId, supplierId, version)}`
  );
}

export async function createSupplierExtractionProfileVersion(
  clientId: string,
  supplierId: string,
  body: CreateSupplierExtractionProfileRequest
): Promise<SupplierExtractionProfile> {
  return apiRequestJson<SupplierExtractionProfile>(
    `${API_BASE}${supplierExtractionProfilesPath(clientId, supplierId)}`,
    { method: 'POST', body }
  );
}

export async function cloneSupplierExtractionProfile(
  clientId: string,
  supplierId: string,
  body: CloneSupplierExtractionProfileRequest
): Promise<SupplierExtractionProfile> {
  return apiRequestJson<SupplierExtractionProfile>(
    `${API_BASE}${supplierExtractionProfilesClonePath(clientId, supplierId)}`,
    { method: 'POST', body }
  );
}

export async function activateSupplierExtractionProfileVersion(
  clientId: string,
  supplierId: string,
  profileId: string,
  expectedRowVersion?: number | null
): Promise<SupplierExtractionProfile> {
  const qs = buildQueryString([['expected_row_version', expectedRowVersion ?? undefined, { min: 1 }]]);
  return apiRequestJson<SupplierExtractionProfile>(
    `${API_BASE}${supplierExtractionProfileActivatePath(clientId, supplierId, profileId)}${qs}`,
    { method: 'POST' }
  );
}

export async function listSupplierReferenceAnnotations(
  clientId: string,
  supplierId: string,
  imageId: string
): Promise<SupplierReferenceAnnotationsListResponse> {
  return apiRequestJson<SupplierReferenceAnnotationsListResponse>(
    `${API_BASE}${supplierReferenceImageAnnotationsPath(clientId, supplierId, imageId)}`
  );
}

export async function replaceSupplierReferenceAnnotations(
  clientId: string,
  supplierId: string,
  imageId: string,
  body: ReplaceSupplierReferenceAnnotationsRequest
): Promise<SupplierReferenceAnnotationsListResponse> {
  return apiRequestJson<SupplierReferenceAnnotationsListResponse>(
    `${API_BASE}${supplierReferenceImageAnnotationsPath(clientId, supplierId, imageId)}`,
    { method: 'PUT', body }
  );
}
