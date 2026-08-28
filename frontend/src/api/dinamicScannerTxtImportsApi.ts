/**
 * Dinamic Scanner TXT aisle import (ESP32 device export, no images).
 */

import { V3_INVENTORIES_BASE } from '../constants/v3ApiPaths';
import { apiRequestJson } from './request';
import type { DinamicScannerTxtImportResponse } from './types';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

function txtImportsBase(inventoryId: string): string {
  return `${API_BASE}${V3_INVENTORIES_BASE}/${encodeURIComponent(inventoryId)}/dinamic-scanner-txt-imports`;
}

/** POST …/dinamic-scanner-txt-imports/preview — multipart field `file`. */
export async function previewDinamicScannerTxtImport(
  inventoryId: string,
  file: File,
  signal?: AbortSignal
): Promise<DinamicScannerTxtImportResponse> {
  const form = new FormData();
  form.append('file', file, file.name);
  return apiRequestJson<DinamicScannerTxtImportResponse>(`${txtImportsBase(inventoryId)}/preview`, {
    method: 'POST',
    body: form,
    signal,
  });
}

/** POST …/dinamic-scanner-txt-imports/confirm */
export async function confirmDinamicScannerTxtImport(
  inventoryId: string,
  body: { export_id: string; conflict_policy?: 'SKIP' | 'REJECT' },
  signal?: AbortSignal
): Promise<DinamicScannerTxtImportResponse> {
  return apiRequestJson<DinamicScannerTxtImportResponse>(`${txtImportsBase(inventoryId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: {
      export_id: body.export_id,
      conflict_policy: body.conflict_policy ?? 'SKIP',
    },
    signal,
  });
}

export function isTxtImportFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.txt');
}

export function isZipImportFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.zip');
}
