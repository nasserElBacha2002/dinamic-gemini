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

/**
 * Phase 9 corrections: network drain worker.
 * Advances uploads natively; wakes JS runtime for entity-directed remote ops when process is alive.
 *
 * Operations that can advance without UI when native/JS runtime is available:
 * UPLOAD_ASSET (native), SYNC/FINALIZE/PROCESS/REPROCESS/REVISION (JS scheduler when process alive).
 * UI still required for: conflict resolution, manual review, adoption decisions.
 */
class OfflineOpsDrainWorker(
  appContext: Context,
  params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
  override suspend fun doWork(): Result {
    Log.i(TAG, "drain start")
    OfflineOpsLocalRecoveryWorker.schedule(applicationContext, expedited = false)
    DinamicUploadWorker.scheduleQueue(applicationContext)
    Log.i(TAG, "drain scheduled upload queue + local recovery")
    return Result.success()
  }

  companion object {
    const val UNIQUE_NAME = "dinamic-offline-operations"
    private const val TAG = "OfflineOpsDrain"

    fun schedule(context: Context, expedited: Boolean = false) {
      val constraints =
        Constraints.Builder()
          .setRequiredNetworkType(NetworkType.CONNECTED)
          .build()
      val builder =
        OneTimeWorkRequestBuilder<OfflineOpsDrainWorker>()
          .setConstraints(constraints)
          .addTag(UNIQUE_NAME)
      if (expedited) {
        builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
      }
      WorkManager.getInstance(context).enqueueUniqueWork(
        UNIQUE_NAME,
        ExistingWorkPolicy.KEEP,
        builder.build(),
      )
      Log.i(TAG, "scheduled unique=$UNIQUE_NAME expedited=$expedited")
    }
  }
}
