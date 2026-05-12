import {
  pathToClientSuppliersBase,
  supplierPromptConfigActivatePath,
  supplierPromptConfigByIdPath,
  supplierPromptConfigsActivePath,
  supplierPromptConfigsPath,
  supplierReferenceImageFilePath,
  supplierReferenceImagesPath,
  supplierReferenceImagePath,
  V3_CLIENTS_BASE,
} from '../constants/v3ApiPaths';
import type {
  ApiErrorDetail,
  ClientSupplier,
  ClientSuppliersListResponse,
  CreateSupplierPromptConfigRequest,
  CreateClientSupplierRequest,
  DeleteSupplierReferenceImageResponse,
  SupplierPromptConfig,
  SupplierPromptConfigsListResponse,
  SupplierReferenceImagesListResponse,
  UploadSupplierReferenceImagesRequest,
  UploadSupplierReferenceImagesResponse,
} from './types';
import { handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';
import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface ClientSuppliersListQuery {
  page?: number;
  page_size?: number;
}

function buildClientSuppliersListQueryString(q: ClientSuppliersListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.page != null && q.page >= 1) params.set('page', String(q.page));
  if (q.page_size != null && q.page_size >= 1) params.set('page_size', String(q.page_size));
  const s = params.toString();
  return s ? `?${s}` : '';
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
  const response = await protectedFetch(
    `${API_BASE}${supplierReferenceImagesPath(clientId, supplierId)}`,
    { method: 'POST', body: form }
  );
  return handleResponse<UploadSupplierReferenceImagesResponse>(response);
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

export async function fetchSupplierReferenceImageFile(
  clientId: string,
  supplierId: string,
  imageId: string
): Promise<{ imageSrc: string; revoke: () => void }> {
  const response = await protectedFetch(
    `${API_BASE}${supplierReferenceImageFilePath(clientId, supplierId, imageId)}`
  );
  if (!response.ok) {
    const text = await response.text();
    let data: ApiErrorDetail;
    try {
      data = (text ? JSON.parse(text) : {}) as ApiErrorDetail;
    } catch {
      data = {};
    }
    throwApiErrorIfNotOk(response, text, data);
  }
  const blob = await response.blob();
  const imageSrc = URL.createObjectURL(blob);
  return {
    imageSrc,
    revoke: () => URL.revokeObjectURL(imageSrc),
  };
}

export interface SupplierPromptConfigsListQuery {
  scope?: 'all';
  provider_name?: string | null;
  model_name?: string | null;
}

function buildSupplierPromptConfigsQueryString(q: SupplierPromptConfigsListQuery | undefined): string {
  if (!q) return '';
  const params = new URLSearchParams();
  if (q.scope === 'all') params.set('scope', 'all');
  const provider = (q.provider_name ?? '').trim();
  const model = (q.model_name ?? '').trim();
  if (provider) params.set('provider_name', provider);
  if (model) params.set('model_name', model);
  const s = params.toString();
  return s ? `?${s}` : '';
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
  const params = new URLSearchParams();
  const normalizedProviderName = (providerName ?? '').trim();
  if (normalizedProviderName) params.set('provider_name', normalizedProviderName);
  const normalizedModelName = (modelName ?? '').trim();
  if (normalizedModelName) params.set('model_name', normalizedModelName);
  return apiRequestJson<SupplierPromptConfig>(
    `${API_BASE}${supplierPromptConfigsActivePath(clientId, supplierId)}?${params.toString()}`
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
