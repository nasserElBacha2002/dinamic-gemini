import * as FileSystem from 'expo-file-system';

/** Durable staging root under documentDirectory (survives cache eviction). */
export function exportStagingRoot(): string {
  const base = FileSystem.documentDirectory;
  if (!base) {
    throw new Error('EXPORT_STAGING_UNAVAILABLE: documentDirectory no disponible');
  }
  return `${base}export-staging/`;
}

export function exportStagingSessionDir(sessionId: string): string {
  const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `${exportStagingRoot()}${safe}/`;
}

export function exportStagingPhotosDir(sessionId: string): string {
  return `${exportStagingSessionDir(sessionId)}photos/`;
}

export function exportStagingPhotoPath(sessionId: string, exportFileName: string): string {
  return `${exportStagingPhotosDir(sessionId)}${exportFileName}`;
}

export async function ensureExportStagingDirs(sessionId: string): Promise<void> {
  await FileSystem.makeDirectoryAsync(exportStagingPhotosDir(sessionId), {
    intermediates: true,
  }).catch(() => undefined);
}

/**
 * Copy source → versioned path (never delete a previous valid final before success).
 * SQLite should be updated to the returned URI only after this resolves.
 * Does not delete or modify the original MediaStore file.
 */
export async function stageOriginalPhotoVersioned(input: {
  readonly sessionId: string;
  readonly sourceUri: string;
  readonly exportFileName: string;
  readonly previousStagingUri?: string | null;
}): Promise<{ readonly stagingUri: string; readonly sizeBytes: number }> {
  await ensureExportStagingDirs(input.sessionId);
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const versionedName = `${input.exportFileName}.v-${stamp}`;
  const finalUri = exportStagingPhotoPath(input.sessionId, versionedName);
  const tmpUri = `${finalUri}.tmp`;

  const sourceInfo = await FileSystem.getInfoAsync(input.sourceUri, { size: true });
  if (!sourceInfo.exists) {
    throw Object.assign(new Error('EXPORT_PREP_SOURCE_MISSING'), {
      code: 'EXPORT_PREP_SOURCE_MISSING',
    });
  }

  await FileSystem.copyAsync({ from: input.sourceUri, to: tmpUri });
  const tmpInfo = await FileSystem.getInfoAsync(tmpUri, { size: true });
  const sizeBytes =
    tmpInfo.exists && typeof tmpInfo.size === 'number' ? tmpInfo.size : 0;
  if (!(sizeBytes > 0)) {
    await FileSystem.deleteAsync(tmpUri, { idempotent: true }).catch(() => undefined);
    throw Object.assign(new Error('EXPORT_PREP_EMPTY_COPY'), {
      code: 'EXPORT_PREP_EMPTY_COPY',
    });
  }

  await FileSystem.moveAsync({ from: tmpUri, to: finalUri });

  // Best-effort cleanup of previous version after successful publish.
  if (
    input.previousStagingUri &&
    input.previousStagingUri !== finalUri &&
    input.previousStagingUri.includes('/export-staging/')
  ) {
    await FileSystem.deleteAsync(input.previousStagingUri, { idempotent: true }).catch(
      () => undefined,
    );
  }

  return { stagingUri: finalUri, sizeBytes };
}

/** @deprecated Use stageOriginalPhotoVersioned — kept name alias for call sites. */
export const stageOriginalPhotoAtomic = stageOriginalPhotoVersioned;

export async function stagingFileExists(uri: string | null | undefined): Promise<boolean> {
  if (!uri) return false;
  try {
    const info = await FileSystem.getInfoAsync(uri, { size: true });
    return Boolean(info.exists && typeof info.size === 'number' && info.size > 0);
  } catch {
    return false;
  }
}

/**
 * Delete staging for a session. Call only on explicit session purge — never on share-dialog
 * cancel. Post-export retention: keep staging until purge so re-export can reuse READY jobs.
 */
export async function deleteSessionExportStaging(sessionId: string): Promise<void> {
  const dir = exportStagingSessionDir(sessionId);
  await FileSystem.deleteAsync(dir, { idempotent: true }).catch(() => undefined);
}

/** Best-effort purge of abandoned `*.tmp` / `*.tmp.*` under export-staging. */
export async function cleanupAbandonedExportStagingTemps(maxAgeMs = 24 * 60 * 60 * 1000): Promise<number> {
  const root = exportStagingRoot();
  let removed = 0;
  try {
    const sessions = await FileSystem.readDirectoryAsync(root);
    const now = Date.now();
    for (const session of sessions) {
      const photosDir = `${root}${session}/photos/`;
      let entries: string[] = [];
      try {
        entries = await FileSystem.readDirectoryAsync(photosDir);
      } catch {
        continue;
      }
      for (const name of entries) {
        if (!name.includes('.tmp')) continue;
        const uri = `${photosDir}${name}`;
        try {
          const info = await FileSystem.getInfoAsync(uri, { size: true, md5: false });
          const mod = info.exists && 'modificationTime' in info ? Number(info.modificationTime) : 0;
          if (mod > 0 && now - mod * 1000 < maxAgeMs) continue;
          await FileSystem.deleteAsync(uri, { idempotent: true });
          removed += 1;
        } catch {
          // ignore
        }
      }
    }
  } catch {
    // root may not exist yet
  }
  return removed;
}

/** Free bytes heuristic; null if unknown. */
export async function getFreeDiskBytesHint(): Promise<number | null> {
  try {
    const root = FileSystem.documentDirectory;
    if (!root) return null;
    // Expo FS 17 has no free-space API — return null so callers warn without blocking incorrectly.
    return null;
  } catch {
    return null;
  }
}
