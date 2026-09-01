/** Portable offline aisle package — format identity (Phase 4). */

export const OFFLINE_AISLE_FORMAT = 'DINAMIC_OFFLINE_AISLE' as const;
export const OFFLINE_AISLE_SCHEMA_VERSION = 1 as const;

/** Legacy CSV/ZIP export kind — unchanged for compatibility. */
export const LEGACY_SESSION_PACKAGE_KIND = 'DINAMIC_LOCAL_AISLE_EXPORT' as const;

export const OFFLINE_AISLE_EXPORT_DIR = 'offline-aisle-exports';

/** Zip safety limits (aligned with backend preparatory validator). */
export const PACKAGE_MAX_FILES = 10_000;
export const PACKAGE_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024;
export const PACKAGE_MAX_SINGLE_FILE_BYTES = 32 * 1024 * 1024;
