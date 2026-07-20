/**
 * v3 REST URL path prefixes (after ``VITE_API_BASE_URL``).
 * Must stay aligned with backend ``APIRouter`` prefixes under ``/api/v3``.
 */

export const V3_API_PREFIX = '/api/v3';

export const V3_INVENTORIES_BASE = `${V3_API_PREFIX}/inventories`;
export const V3_CLIENTS_BASE = `${V3_API_PREFIX}/clients`;
export const V3_ADMIN_BASE = `${V3_API_PREFIX}/admin`;
export const V3_ANALYTICS_BASE = `${V3_API_PREFIX}/analytics`;
export const V3_OBSERVABILITY_BASE = `${V3_API_PREFIX}/observability`;

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

/** GET …/reference-images/{imageId}/image-display-url */
export function supplierReferenceImageDisplayUrlPath(
  clientId: string,
  supplierId: string,
  imageId: string
): string {
  return `${supplierReferenceImagePath(clientId, supplierId, imageId)}/image-display-url`;
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

/** GET|POST .../clients/{clientId}/suppliers/{supplierId}/extraction-profiles */
export function supplierExtractionProfilesPath(clientId: string, supplierId: string): string {
  return `${pathToClientSuppliersBase(clientId)}/${encodeURIComponent(supplierId)}/extraction-profiles`;
}

/** GET .../extraction-profiles/active */
export function supplierExtractionProfilesActivePath(clientId: string, supplierId: string): string {
  return `${supplierExtractionProfilesPath(clientId, supplierId)}/active`;
}

/** GET .../extraction-profiles/versions/{version} */
export function supplierExtractionProfileByVersionPath(
  clientId: string,
  supplierId: string,
  version: number
): string {
  return `${supplierExtractionProfilesPath(clientId, supplierId)}/versions/${encodeURIComponent(String(version))}`;
}

/** POST .../extraction-profiles/clone */
export function supplierExtractionProfilesClonePath(clientId: string, supplierId: string): string {
  return `${supplierExtractionProfilesPath(clientId, supplierId)}/clone`;
}

/** POST .../extraction-profiles/{profileId}/activate */
export function supplierExtractionProfileActivatePath(
  clientId: string,
  supplierId: string,
  profileId: string
): string {
  return `${supplierExtractionProfilesPath(clientId, supplierId)}/${encodeURIComponent(profileId)}/activate`;
}

/** GET|PUT .../reference-images/{imageId}/annotations */
export function supplierReferenceImageAnnotationsPath(
  clientId: string,
  supplierId: string,
  imageId: string
): string {
  return `${supplierReferenceImagePath(clientId, supplierId, imageId)}/annotations`;
}

