/** Portable offline aisle package — format identity (Phase 4). */

export const OFFLINE_AISLE_FORMAT = 'DINAMIC_OFFLINE_AISLE' as const;
/** Historical schema v1 layout (aisle.json, profiles, per-capture files). */
export const OFFLINE_AISLE_SCHEMA_VERSION = 1 as const;
export const OFFLINE_AISLE_SCHEMA_VERSION_V2 = 2 as const;
/** Schema version written by current mobile export. */
export const OFFLINE_AISLE_EXPORT_SCHEMA_VERSION = OFFLINE_AISLE_SCHEMA_VERSION_V2;
export const OFFLINE_AISLE_PACKAGE_PAYLOAD_PATH = 'aisle-package.json' as const;

/** Legacy CSV/ZIP export kind — unchanged for compatibility. */
export const LEGACY_SESSION_PACKAGE_KIND = 'DINAMIC_LOCAL_AISLE_EXPORT' as const;

export const OFFLINE_AISLE_EXPORT_DIR = 'offline-aisle-exports';

/** Zip safety limits (aligned with backend preparatory validator). */
export const PACKAGE_MAX_FILES = 10_000;
export const PACKAGE_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024;
export const PACKAGE_MAX_SINGLE_FILE_BYTES = 32 * 1024 * 1024;
