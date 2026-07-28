package com.dinamic.capturefgs

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters

/**
 * Backward-compatible alias: previous unique work name still maps here,
 * then delegates to LocalRecovery + Drain.
 */
class OfflineOpsRecoveryWorker(
  appContext: Context,
  params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
  override suspend fun doWork(): Result {
    Log.i(TAG, "legacy recovery alias → local + drain")
    OfflineOpsLocalRecoveryWorker.schedule(applicationContext, expedited = false)
    OfflineOpsDrainWorker.schedule(applicationContext, expedited = false)
    return Result.success()
  }

  companion object {
    const val UNIQUE_NAME = "dinamic-offline-operations-legacy"
    private const val TAG = "OfflineOpsRecovery"

    fun schedule(context: Context, expedited: Boolean = false) {
      OfflineOpsLocalRecoveryWorker.schedule(context, expedited = expedited)
      OfflineOpsDrainWorker.schedule(context, expedited = expedited)
    }
  }
}
