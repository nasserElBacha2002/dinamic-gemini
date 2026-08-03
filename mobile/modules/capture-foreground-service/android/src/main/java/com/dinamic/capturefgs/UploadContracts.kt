package com.dinamic.capturefgs

/**
 * Shared contracts between Kotlin native worker and TypeScript UploadQueue / AisleAssetsApi.
 * Keep in sync with mobile/src/core/uploadLease.ts and aisleAssetsApi.ts.
 */
object UploadContracts {
  const val UNIQUE_QUEUE_NAME = "dinamic-upload-queue"
  const val WORK_TAG = "dinamic-upload"
  const val NOTIFICATION_CHANNEL_ID = "dinamic_upload_wm"
  const val NOTIFICATION_ID = 42002
  /** Requires v19 ordered-capture columns for native multipart parity with JS. */
  const val MIN_SCHEMA_VERSION = 19

  const val OWNER_NATIVE = "native"
  const val OWNER_JS = "js"
  const val LEASE_TTL_MS = 180_000L
  const val HEARTBEAT_INTERVAL_MS = 30_000L

  const val MULTIPART_FIELD_BATCH = "upload_batch_id"
  const val MULTIPART_FIELD_CLIENT_IDS = "client_file_ids"
  const val MULTIPART_FIELD_ORDERED_SESSION = "ordered_capture_session_id"
  const val MULTIPART_FIELD_SEQUENCE_NUMBERS = "sequence_numbers"
  const val MULTIPART_FIELD_FILES = "files"

  const val CODE_AUTH_REQUIRED = "AUTH_REQUIRED"
  const val CODE_AUTH_VAULT_UNAVAILABLE = "AUTH_VAULT_UNAVAILABLE"
  const val CODE_DB_MIGRATION_REQUIRED = "DB_MIGRATION_REQUIRED"
  const val CODE_UPLOAD_REPREPARE_REQUIRED = "UPLOAD_REPREPARE_REQUIRED"
  const val CODE_REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
  const val CODE_REQUEST_CANCELLED = "REQUEST_CANCELLED"
  const val CODE_NETWORK_ERROR = "NETWORK_ERROR"
  const val CODE_FILE_MISSING = "FILE_MISSING"
  const val CODE_TLS_ERROR = "TLS_ERROR"
  const val CODE_RESPONSE_PARSE_ERROR = "RESPONSE_PARSE_ERROR"
  const val CODE_QUEUE_PAUSED = "PAUSED"

  fun assetsPath(inventoryId: String, aisleId: String): String =
    "/api/v3/inventories/$inventoryId/aisles/$aisleId/assets"

  fun processPath(inventoryId: String, aisleId: String): String =
    "/api/v3/inventories/$inventoryId/aisles/$aisleId/process"

  fun sealOrderedCapturePath(orderedCaptureSessionId: String): String =
    "/api/v3/inventories/ordered-capture-sessions/$orderedCaptureSessionId/seal"

  fun backgroundProcessIdempotencyKey(sessionId: String): String =
    "mobile-process-bg:$sessionId"
}
