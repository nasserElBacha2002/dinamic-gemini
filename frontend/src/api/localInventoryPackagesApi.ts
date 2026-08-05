/**
 * Local inventory ZIP package import (CSV + photos from mobile export).
 */

import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';
import type { LocalInventoryPackageResponse } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

function packagesBase(inventoryId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/local-inventory-packages`;
}

/** POST …/local-inventory-packages/preview — multipart field `file`. */
export async function previewLocalInventoryPackage(
  inventoryId: string,
  file: File,
  signal?: AbortSignal
): Promise<LocalInventoryPackageResponse> {
  const form = new FormData();
  form.append('file', file, file.name);
  return apiRequestJson<LocalInventoryPackageResponse>(`${packagesBase(inventoryId)}/preview`, {
    method: 'POST',
    body: form,
    signal,
  });
}

/** POST …/local-inventory-packages/confirm */
export async function confirmLocalInventoryPackage(
  inventoryId: string,
  body: { export_id: string; conflict_policy?: 'SKIP' | 'REJECT' },
  signal?: AbortSignal
): Promise<LocalInventoryPackageResponse> {
  return apiRequestJson<LocalInventoryPackageResponse>(`${packagesBase(inventoryId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: {
      export_id: body.export_id,
      conflict_policy: body.conflict_policy ?? 'SKIP',
    },
    signal,
  });
}

/** GET …/local-inventory-packages/{package_id} */
export async function getLocalInventoryPackage(
  inventoryId: string,
  packageId: string,
  signal?: AbortSignal
): Promise<LocalInventoryPackageResponse> {
  return apiRequestJson<LocalInventoryPackageResponse>(
    `${packagesBase(inventoryId)}/${encodeURIComponent(packageId)}`,
    { method: 'GET', signal }
  );
}
