/**
 * v3 REST URL path prefixes (after ``VITE_API_BASE_URL``).
 * Must stay aligned with backend ``APIRouter`` prefixes under ``/api/v3``.
 */

export const V3_API_PREFIX = '/api/v3';

export const V3_INVENTORIES_BASE = `${V3_API_PREFIX}/inventories`;
export const V3_CLIENTS_BASE = `${V3_API_PREFIX}/clients`;
export const V3_ADMIN_BASE = `${V3_API_PREFIX}/admin`;
export const V3_ANALYTICS_BASE = `${V3_API_PREFIX}/analytics`;
export const V3_REVIEW_QUEUE_BASE = `${V3_API_PREFIX}/review-queue`;

export function pathToClientSuppliersBase(clientId: string): string {
  return `${V3_CLIENTS_BASE}/${encodeURIComponent(clientId)}/suppliers`;
}

/** GET|POST …/clients/{clientId}/suppliers/{supplierId}/reference-images */
export function supplierReferenceImagesPath(clientId: string, supplierId: string): string {
  return `${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}/reference-images`;
}

/** DELETE …/reference-images/{imageId} */
export function supplierReferenceImagePath(clientId: string, supplierId: string, imageId: string): string {
  return `${supplierReferenceImagesPath(clientId, supplierId)}/${encodeURIComponent(imageId)}`;
}

/** GET …/reference-images/{imageId}/file */
export function supplierReferenceImageFilePath(clientId: string, supplierId: string, imageId: string): string {
  return `${supplierReferenceImagePath(clientId, supplierId, imageId)}/file`;
}

/** GET|POST .../clients/{clientId}/suppliers/{supplierId}/prompt-configs */
export function supplierPromptConfigsPath(clientId: string, supplierId: string): string {
  return `${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}/prompt-configs`;
}

/** GET .../prompt-configs/active */
export function supplierPromptConfigsActivePath(clientId: string, supplierId: string): string {
  return `${supplierPromptConfigsPath(clientId, supplierId)}/active`;
}

/** GET .../prompt-configs/{configId} */
export function supplierPromptConfigByIdPath(
  clientId: string,
  supplierId: string,
  configId: string
): string {
  return `${supplierPromptConfigsPath(clientId, supplierId)}/${encodeURIComponent(configId)}`;
}

/** POST .../prompt-configs/{configId}/activate */
export function supplierPromptConfigActivatePath(
  clientId: string,
  supplierId: string,
  configId: string
): string {
  return `${supplierPromptConfigByIdPath(clientId, supplierId, configId)}/activate`;
}
