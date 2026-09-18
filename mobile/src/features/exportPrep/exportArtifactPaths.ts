/**
 * Central path helpers for aisle-exports + quarantine (Phase 6).
 * Do not duplicate naming conventions elsewhere.
 */

import * as FileSystem from 'expo-file-system';

export const AISLE_EXPORTS_DIR_NAME = 'aisle-exports';
export const EXPORT_QUARANTINE_DIR_NAME = 'export-quarantine';

export function aisleExportsRoot(): string {
  const base = FileSystem.documentDirectory ?? FileSystem.cacheDirectory;
  if (!base) {
    throw new Error('AISLE_EXPORTS_UNAVAILABLE: no document/cache directory');
  }
  return `${base}${AISLE_EXPORTS_DIR_NAME}/`;
}

export function exportQuarantineRoot(): string {
  const base = FileSystem.documentDirectory;
  if (!base) {
    throw new Error('EXPORT_QUARANTINE_UNAVAILABLE: documentDirectory no disponible');
  }
  return `${base}${EXPORT_QUARANTINE_DIR_NAME}/`;
}

export async function ensureAisleExportsDir(): Promise<string> {
  const dir = aisleExportsRoot();
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
  return dir;
}

export async function ensureExportQuarantineDir(): Promise<string> {
  const dir = exportQuarantineRoot();
  await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
  return dir;
}

export function buildExportPublishPaths(input: {
  readonly exportId: string;
  readonly publishToken: string;
}): {
  readonly dir: string;
  readonly csvUri: string;
  readonly zipUri: string;
  readonly tmpCsv: string;
  readonly tmpZip: string;
} {
  const dir = aisleExportsRoot();
  const base = `${dir}${input.exportId}.${input.publishToken}`;
  return {
    dir,
    csvUri: `${base}.csv`,
    zipUri: `${base}.zip`,
    tmpCsv: `${base}.tmp.csv`,
    tmpZip: `${base}.tmp.zip`,
  };
}

/** Non-colliding quarantine name preserving extension. */
export function buildQuarantineFileName(input: {
  readonly originalName: string;
  readonly reasonCode: string;
  readonly nowMs?: number;
}): string {
  const stamp = input.nowMs ?? Date.now();
  const rand = Math.random().toString(36).slice(2, 10);
  const safeReason = input.reasonCode.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40);
  const safeName = input.originalName.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 80);
  return `${stamp}-${rand}-${safeReason}-${safeName}`;
}

export function isAisleExportTempName(name: string): boolean {
  return name.endsWith('.tmp.zip') || name.endsWith('.tmp.csv') || name.includes('.tmp.');
}

export function isAisleExportFinalName(name: string): boolean {
  if (isAisleExportTempName(name)) return false;
  return name.endsWith('.zip') || name.endsWith('.csv');
}
