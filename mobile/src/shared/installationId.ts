/**
 * Persistent installation / device identity for CSV export and upload metadata.
 * Never use app version or environment as a device id.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

import { createId } from './createId';

const INSTALLATION_ID_KEY = 'dinamic.installation_id';

let cachedInstallationId: string | null = null;

export async function getOrCreateInstallationId(): Promise<string> {
  if (cachedInstallationId) {
    return cachedInstallationId;
  }
  try {
    const existing = await AsyncStorage.getItem(INSTALLATION_ID_KEY);
    if (existing && existing.trim().length > 0) {
      cachedInstallationId = existing.trim();
      return cachedInstallationId;
    }
  } catch {
    // fall through to create
  }
  const created = createId();
  cachedInstallationId = created;
  try {
    await AsyncStorage.setItem(INSTALLATION_ID_KEY, created);
  } catch {
    // in-memory still usable for this process
  }
  return created;
}

/** Test helper — clear cached id. */
export function resetInstallationIdCacheForTests(): void {
  cachedInstallationId = null;
}
