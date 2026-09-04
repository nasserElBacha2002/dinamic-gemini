/** Provenance of a row in local_aisles. */
export type LocalAisleOrigin = 'REMOTE' | 'LOCAL';

/** Sync lifecycle — orthogonal to operational aisle status (created, etc.). */
export type LocalAisleSyncStatus = 'REMOTE_SYNCED' | 'LOCAL_ONLY';

export interface LocalAisleMetadata {
  readonly origin: LocalAisleOrigin;
  readonly sync_status: LocalAisleSyncStatus;
  readonly client_supplier_id: string | null;
  readonly created_offline_at: string | null;
}
