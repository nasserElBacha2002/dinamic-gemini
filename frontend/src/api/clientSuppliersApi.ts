import {
  pathToClientSuppliersBase,
  supplierReferenceImageFilePath,
  supplierReferenceImagesPath,
  supplierReferenceImagePath,
  V3_CLIENTS_BASE,
} from '../constants/v3ApiPaths';
import type {
  ApiErrorDetail,
  ClientSupplier,
  ClientSuppliersListResponse,
  CreateClientSupplierRequest,
  DeleteSupplierReferenceImageResponse,
  SupplierReferenceImagesListResponse,
  UploadSupplierReferenceImagesRequest,
  UploadSupplierReferenceImagesResponse,
} from './types';
import { handleResponse, protectedFetch, throwApiErrorIfNotOk } from './http';

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
  const response = await protectedFetch(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}${qs}`
  );
  return handleResponse<ClientSuppliersListResponse>(response);
}

export async function getClientSupplier(
  clientId: string,
  supplierId: string
): Promise<ClientSupplier> {
  const response = await protectedFetch(
    `${API_BASE}${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}`
  );
  return handleResponse<ClientSupplier>(response);
}

export async function createClientSupplier(
  clientId: string,
  body: CreateClientSupplierRequest
): Promise<ClientSupplier> {
  const response = await protectedFetch(
    `${API_BASE}${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/suppliers`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  );
  return handleResponse<ClientSupplier>(response);
}

export async function listSupplierReferenceImages(
  clientId: string,
  supplierId: string
): Promise<SupplierReferenceImagesListResponse> {
  const response = await protectedFetch(
    `${API_BASE}${supplierReferenceImagesPath(clientId, supplierId)}`
  );
  return handleResponse<SupplierReferenceImagesListResponse>(response);
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
  const response = await protectedFetch(
    `${API_BASE}${supplierReferenceImagePath(clientId, supplierId, imageId)}`,
    { method: 'DELETE' }
  );
  return handleResponse<DeleteSupplierReferenceImageResponse>(response);
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
