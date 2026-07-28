package com.dinamic.capturefgs

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.time.Instant

/**
 * Phase 9 corrections: local recovery WITHOUT network constraint.
 * Recovers expired leases / abandoned RUNNING; marks auth-required ops when vault missing.
 */
class OfflineOpsLocalRecoveryWorker(
  appContext: Context,
  params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
  override suspend fun doWork(): Result {
    Log.i(TAG, "local recovery start")
    val store = UploadSqliteStore(applicationContext)
    val now = Instant.now().toString()
    when (val opened = store.open()) {
      is UploadSqliteStore.OpenResult.Failed -> {
        // Still succeed — local ledger recovery can wait for DB; do not require auth vault.
        Log.w(TAG, "sqlite unavailable (non-fatal): ${opened.code} ${opened.message}")
        return Result.success()
      }
      is UploadSqliteStore.OpenResult.Ok -> {
        opened.db.use { db ->
          try {
            db.execSQL(
              """
              UPDATE offline_operations
              SET status = 'READY',
                  owner_token = NULL,
                  lease_expires_at = NULL,
                  heartbeat_at = NULL,
                  updated_at = ?,
                  last_error_code = 'RECOVERED_EXPIRED_LEASE'
              WHERE status = 'RUNNING'
                AND (lease_expires_at IS NULL OR lease_expires_at < ?)
              """.trimIndent(),
              arrayOf(now, now),
            )
            val hasAuth =
              AuthVault.read(applicationContext).available &&
                !AuthVault.read(applicationContext).accessToken.isNullOrBlank()
            if (!hasAuth) {
              db.execSQL(
                """
                UPDATE offline_operations
                SET status = 'BLOCKED_AUTH',
                    updated_at = ?,
                    last_error_code = 'AUTH_REQUIRED'
                WHERE requires_auth = 1
                  AND status IN ('PENDING', 'READY', 'RETRY_WAIT')
                """.trimIndent(),
                arrayOf(now),
              )
            }
            db.execSQL(
              """
              UPDATE aisle_finalization_intents
              SET status = 'FINALIZATION_PENDING', updated_at = ?
              WHERE status = 'FINALIZATION_SYNCING'
              """.trimIndent(),
              arrayOf(now),
            )
          } catch (e: Exception) {
            Log.w(TAG, "local recovery SQL skipped/failed: ${e.message}")
          }
        }
      }
    }
    Log.i(TAG, "local recovery done")
    return Result.success()
  }

  companion object {
    const val UNIQUE_NAME = "dinamic-offline-local-recovery"
    private const val TAG = "OfflineOpsLocalRecovery"

    fun schedule(context: Context, expedited: Boolean = false) {
      // No network constraint — recovery must run offline / without auth.
      val builder =
        OneTimeWorkRequestBuilder<OfflineOpsLocalRecoveryWorker>()
          .addTag(UNIQUE_NAME)
      if (expedited) {
        builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
      }
      WorkManager.getInstance(context).enqueueUniqueWork(
        UNIQUE_NAME,
        ExistingWorkPolicy.KEEP,
        builder.build(),
      )
      Log.i(TAG, "scheduled unique=$UNIQUE_NAME")
    }
  }
}
