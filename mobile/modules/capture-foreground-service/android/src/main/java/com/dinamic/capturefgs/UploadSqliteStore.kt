package com.dinamic.capturefgs

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.Log
import java.io.File
import java.util.UUID

/**
 * Direct SQLite access to the Expo `dinamic_mobile.db` for native upload drain.
 * Contract mirrors TS CaptureRepository lease helpers.
 */
class UploadSqliteStore(private val context: Context) {
  data class EligiblePhoto(
    val id: String,
    val sessionId: String,
    val inventoryId: String,
    val aisleId: String,
    val uploadBatchId: String,
    val clientFileId: String,
    val uri: String,
    val transformUri: String?,
    val displayName: String,
    val mimeType: String,
    val uploadSize: Long,
    val uploadAttempts: Int,
  )

  data class UploadOk(val clientFileId: String, val assetId: String)
  data class UploadErr(val clientFileId: String?, val code: String?, val detail: String?)

  data class SessionForProcess(
    val sessionId: String,
    val inventoryId: String,
    val aisleId: String,
    val preparationProcessingMode: String?,
  )

  sealed class OpenResult {
    data class Ok(val db: SQLiteDatabase) : OpenResult()
    data class Failed(val code: String, val message: String) : OpenResult()
  }

  fun open(): OpenResult {
    val authPath = AuthVault.read(context).sqliteDbPath?.takeIf { it.isNotBlank() }
    val candidates = buildList {
      if (authPath != null) add(File(authPath))
      add(File(context.filesDir, "SQLite/dinamic_mobile.db"))
      add(context.getDatabasePath("dinamic_mobile.db"))
      add(File(context.filesDir, "dinamic_mobile.db"))
    }
    for (file in candidates) {
      if (!file.exists()) continue
      return try {
        val db = SQLiteDatabase.openDatabase(
          file.absolutePath,
          null,
          SQLiteDatabase.OPEN_READWRITE or SQLiteDatabase.ENABLE_WRITE_AHEAD_LOGGING,
        )
        db.rawQuery("PRAGMA busy_timeout=5000;", null).close()
        val version = schemaVersion(db)
        if (version < UploadContracts.MIN_SCHEMA_VERSION) {
          db.close()
          OpenResult.Failed(
            UploadContracts.CODE_DB_MIGRATION_REQUIRED,
            "schema $version < ${UploadContracts.MIN_SCHEMA_VERSION}",
          )
        } else {
          OpenResult.Ok(db)
        }
      } catch (e: Exception) {
        Log.w(TAG, "open failed: ${e.javaClass.simpleName}")
        OpenResult.Failed("DB_LOCKED", e.message ?: "open failed")
      }
    }
    Log.w(TAG, "dinamic_mobile.db not found")
    return OpenResult.Failed("DB_MISSING", "database not found")
  }

  fun schemaVersion(db: SQLiteDatabase): Int {
    return try {
      db.rawQuery("SELECT MAX(version) FROM schema_migrations", null).use { c ->
        if (c.moveToFirst() && !c.isNull(0)) c.getInt(0) else 0
      }
    } catch (e: Exception) {
      Log.w(TAG, "schema_migrations missing: ${e.javaClass.simpleName}")
      0
    }
  }

  fun listEligiblePrepared(db: SQLiteDatabase, limit: Int, nowIso: String): List<EligiblePhoto> {
    val sql = """
      SELECT p.id, p.capture_session_id, s.inventory_id, s.aisle_id, s.upload_batch_id,
             p.client_file_id, p.uri, p.local_transform_uri, p.display_name, p.mime_type,
             p.upload_size, p.upload_attempts
      FROM capture_photos p
      INNER JOIN capture_sessions s ON s.id = p.capture_session_id
      WHERE p.status = 'stable'
        AND p.upload_status IN ('queued', 'retryable_error')
        AND COALESCE(p.upload_cancel_requested, 0) = 0
        AND p.upload_size IS NOT NULL AND p.upload_size > 0
        AND p.client_file_id IS NOT NULL
        AND s.upload_batch_id IS NOT NULL
        AND COALESCE(p.last_upload_error_code, '') != '${UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED}'
        AND (p.next_retry_at IS NULL OR p.next_retry_at <= ?)
        AND (
          p.upload_lease_token IS NULL
          OR p.upload_lease_expires_at IS NULL
          OR p.upload_lease_expires_at <= ?
        )
      ORDER BY p.date_added ASC, p.asset_id ASC
      LIMIT ?
    """.trimIndent()
    val out = mutableListOf<EligiblePhoto>()
    db.rawQuery(sql, arrayOf(nowIso, nowIso, limit.toString())).use { c ->
      while (c.moveToNext()) {
        out.add(
          EligiblePhoto(
            id = c.getString(0),
            sessionId = c.getString(1),
            inventoryId = c.getString(2),
            aisleId = c.getString(3),
            uploadBatchId = c.getString(4),
            clientFileId = c.getString(5),
            uri = c.getString(6),
            transformUri = c.getString(7),
            displayName = c.getString(8) ?: "photo.jpg",
            mimeType = c.getString(9) ?: "image/jpeg",
            uploadSize = c.getLong(10),
            uploadAttempts = c.getInt(11),
          ),
        )
      }
    }
    return out
  }

  fun tryAcquireLease(
    db: SQLiteDatabase,
    photoId: String,
    owner: String,
    token: String,
    expiresAt: String,
    nowIso: String,
  ): Boolean {
    db.beginTransaction()
    return try {
      val updated = db.compileStatement(
        """
        UPDATE capture_photos SET
          upload_worker_owner = ?,
          upload_lease_token = ?,
          upload_lease_expires_at = ?,
          upload_heartbeat_at = ?,
          upload_status = 'uploading',
          last_upload_attempt_at = ?,
          upload_attempts = upload_attempts + 1,
          updated_at = ?
        WHERE id = ?
          AND upload_status IN ('queued', 'retryable_error', 'uploading')
          AND COALESCE(upload_cancel_requested, 0) = 0
          AND (
            upload_lease_token IS NULL
            OR upload_lease_expires_at IS NULL
            OR upload_lease_expires_at <= ?
            OR upload_lease_token = ?
          )
        """.trimIndent(),
      ).use { stmt ->
        stmt.bindString(1, owner)
        stmt.bindString(2, token)
        stmt.bindString(3, expiresAt)
        stmt.bindString(4, nowIso)
        stmt.bindString(5, nowIso)
        stmt.bindString(6, nowIso)
        stmt.bindString(7, photoId)
        stmt.bindString(8, nowIso)
        stmt.bindString(9, token)
        stmt.executeUpdateDelete()
      }
      if (updated == 1) {
        db.setTransactionSuccessful()
        true
      } else {
        false
      }
    } finally {
      db.endTransaction()
    }
  }

  /** Renew lease TTL + heartbeat. Returns false if ownership was lost. */
  fun heartbeatLease(
    db: SQLiteDatabase,
    photoId: String,
    token: String,
    expiresAt: String,
    nowIso: String,
  ): Boolean {
    val updated = db.compileStatement(
      """
      UPDATE capture_photos SET
        upload_lease_expires_at = ?,
        upload_heartbeat_at = ?,
        updated_at = ?
      WHERE id = ?
        AND upload_lease_token = ?
        AND COALESCE(upload_cancel_requested, 0) = 0
      """.trimIndent(),
    ).use { stmt ->
      stmt.bindString(1, expiresAt)
      stmt.bindString(2, nowIso)
      stmt.bindString(3, nowIso)
      stmt.bindString(4, photoId)
      stmt.bindString(5, token)
      stmt.executeUpdateDelete()
    }
    return updated == 1
  }

  fun releaseLease(db: SQLiteDatabase, photoId: String, token: String) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(nowIso(), photoId, token),
    )
  }

  fun releaseLeasesForToken(db: SQLiteDatabase, photoIds: List<String>, tokens: List<String>) {
    for (i in photoIds.indices) {
      releaseLease(db, photoIds[i], tokens[i])
    }
  }

  fun markUploaded(
    db: SQLiteDatabase,
    photoId: String,
    token: String,
    assetId: String,
    uploadedAt: String,
  ) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_status = 'uploaded',
        upload_progress = 1,
        backend_asset_id = ?,
        uploaded_at = ?,
        last_upload_error_code = NULL,
        last_upload_error_message = NULL,
        next_retry_at = NULL,
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(assetId, uploadedAt, uploadedAt, photoId, token),
    )
  }

  fun markRetryable(
    db: SQLiteDatabase,
    photoId: String,
    token: String,
    code: String,
    message: String,
    nextRetryAt: String,
  ) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_status = 'retryable_error',
        last_upload_error_code = ?,
        last_upload_error_message = ?,
        next_retry_at = ?,
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(code, message, nextRetryAt, nowIso(), photoId, token),
    )
  }

  /**
   * HTTP 413 / reprepare: clear transform + size so JS must prepare again.
   * Native worker will not re-upload until JS clears UPLOAD_REPREPARE_REQUIRED.
   */
  fun markReprepareRequired(
    db: SQLiteDatabase,
    photoId: String,
    token: String,
    message: String,
  ) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_status = 'retryable_error',
        last_upload_error_code = ?,
        last_upload_error_message = ?,
        local_transform_uri = NULL,
        upload_size = NULL,
        next_retry_at = ?,
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(
        UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED,
        message,
        nowIso(),
        nowIso(),
        photoId,
        token,
      ),
    )
  }

  fun markPermanent(
    db: SQLiteDatabase,
    photoId: String,
    token: String,
    code: String,
    message: String,
  ) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_status = 'permanent_error',
        last_upload_error_code = ?,
        last_upload_error_message = ?,
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(code, message, nowIso(), photoId, token),
    )
  }

  fun isCancelRequested(db: SQLiteDatabase, photoId: String): Boolean {
    db.rawQuery(
      "SELECT COALESCE(upload_cancel_requested, 0) FROM capture_photos WHERE id = ?",
      arrayOf(photoId),
    ).use { c ->
      if (c.moveToFirst()) {
        return c.getInt(0) == 1
      }
    }
    return false
  }

  fun markExcludedAfterCancel(db: SQLiteDatabase, photoId: String, token: String) {
    db.execSQL(
      """
      UPDATE capture_photos SET
        upload_status = 'excluded',
        upload_cancel_requested = 0,
        upload_worker_owner = NULL,
        upload_lease_token = NULL,
        upload_lease_expires_at = NULL,
        upload_heartbeat_at = NULL,
        updated_at = ?
      WHERE id = ? AND upload_lease_token = ?
      """.trimIndent(),
      arrayOf(nowIso(), photoId, token),
    )
  }

  fun countPendingPrepared(db: SQLiteDatabase): Int {
    db.rawQuery(
      """
      SELECT COUNT(*) FROM capture_photos
      WHERE status = 'stable'
        AND upload_status IN ('queued', 'retryable_error', 'uploading')
        AND upload_size IS NOT NULL AND upload_size > 0
        AND COALESCE(last_upload_error_code, '') != '${UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED}'
      """.trimIndent(),
      null,
    ).use { c ->
      return if (c.moveToFirst()) c.getInt(0) else 0
    }
  }

  /** Photos uploaded in this worker run window (same session progress for notification). */
  fun countUploadedForSessions(db: SQLiteDatabase, sessionIds: Collection<String>): Int {
    if (sessionIds.isEmpty()) return 0
    val placeholders = sessionIds.joinToString(",") { "?" }
    db.rawQuery(
      """
      SELECT COUNT(*) FROM capture_photos
      WHERE upload_status = 'uploaded'
        AND capture_session_id IN ($placeholders)
      """.trimIndent(),
      sessionIds.toTypedArray(),
    ).use { c ->
      return if (c.moveToFirst()) c.getInt(0) else 0
    }
  }

  fun countPendingForSessions(db: SQLiteDatabase, sessionIds: Collection<String>): Int {
    if (sessionIds.isEmpty()) return 0
    val placeholders = sessionIds.joinToString(",") { "?" }
    db.rawQuery(
      """
      SELECT COUNT(*) FROM capture_photos
      WHERE status = 'stable'
        AND capture_session_id IN ($placeholders)
        AND upload_status IN ('queued', 'retryable_error', 'uploading')
        AND upload_size IS NOT NULL AND upload_size > 0
        AND COALESCE(last_upload_error_code, '') != '${UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED}'
      """.trimIndent(),
      sessionIds.toTypedArray(),
    ).use { c ->
      return if (c.moveToFirst()) c.getInt(0) else 0
    }
  }

  fun listSessionsReadyForProcess(db: SQLiteDatabase): List<SessionForProcess> {
    val sql = """
      SELECT s.id, s.inventory_id, s.aisle_id, s.preparation_processing_mode
      FROM capture_sessions s
      WHERE s.upload_batch_id IS NOT NULL
        AND (s.backend_job_id IS NULL OR s.backend_job_id = '')
        AND COALESCE(s.processing_status, '') NOT IN ('processing', 'completed', 'starting')
        AND EXISTS (
          SELECT 1 FROM capture_photos p
          WHERE p.capture_session_id = s.id AND p.upload_status = 'uploaded'
        )
        AND NOT EXISTS (
          SELECT 1 FROM capture_photos p
          WHERE p.capture_session_id = s.id
            AND p.status = 'stable'
            AND p.upload_status NOT IN ('uploaded', 'excluded', 'remote_deleted', 'permanent_error')
        )
    """.trimIndent()
    val out = mutableListOf<SessionForProcess>()
    db.rawQuery(sql, null).use { c ->
      while (c.moveToNext()) {
        out.add(
          SessionForProcess(
            sessionId = c.getString(0),
            inventoryId = c.getString(1),
            aisleId = c.getString(2),
            preparationProcessingMode = c.getString(3),
          ),
        )
      }
    }
    return out
  }

  fun markProcessPending(db: SQLiteDatabase, sessionId: String) {
    db.execSQL(
      """
      UPDATE capture_sessions SET
        processing_status = 'process_pending',
        last_processing_error = NULL,
        updated_at = ?
      WHERE id = ?
      """.trimIndent(),
      arrayOf(nowIso(), sessionId),
    )
  }

  fun markProcessStarted(
    db: SQLiteDatabase,
    sessionId: String,
    backendJobId: String,
  ) {
    val now = nowIso()
    db.execSQL(
      """
      UPDATE capture_sessions SET
        backend_job_id = ?,
        processing_status = 'processing',
        status = 'processing',
        processing_started_at = ?,
        last_processing_error = NULL,
        updated_at = ?
      WHERE id = ?
      """.trimIndent(),
      arrayOf(backendJobId, now, now, sessionId),
    )
    val jobLocalId = "native-${UUID.randomUUID()}"
    try {
      db.execSQL(
        """
        INSERT INTO processing_jobs (
          id, capture_session_id, inventory_id, aisle_id, backend_job_id, status, remote_status,
          created_at, started_at, finished_at, last_polled_at, next_poll_at, attempt_count, error_code, error_message
        )
        SELECT ?, id, inventory_id, aisle_id, ?, 'pending', 'queued', ?, ?, NULL, NULL, ?, 0, NULL, NULL
        FROM capture_sessions WHERE id = ?
        """.trimIndent(),
        arrayOf(jobLocalId, backendJobId, now, now, now, sessionId),
      )
    } catch (e: Exception) {
      Log.w(TAG, "processing_jobs insert skipped: ${e.javaClass.simpleName}")
    }
  }

  fun markProcessFailed(db: SQLiteDatabase, sessionId: String, code: String, message: String) {
    db.execSQL(
      """
      UPDATE capture_sessions SET
        processing_status = 'process_pending',
        last_processing_error = ?,
        updated_at = ?
      WHERE id = ?
      """.trimIndent(),
      arrayOf("$code: $message", nowIso(), sessionId),
    )
  }

  companion object {
    private const val TAG = "UploadSqliteStore"

    fun newLeaseToken(): String = "native-${UUID.randomUUID()}"

    fun nowIso(): String = java.time.Instant.now().toString()

    fun leaseExpiresIso(fromMs: Long = System.currentTimeMillis()): String =
      java.time.Instant.ofEpochMilli(fromMs + UploadContracts.LEASE_TTL_MS).toString()
  }
}
