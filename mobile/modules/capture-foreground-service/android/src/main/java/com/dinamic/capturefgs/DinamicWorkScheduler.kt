package com.dinamic.capturefgs

import android.content.Context
import android.util.Log

/**
 * Phase 2: single unique WorkManager queue `dinamic-upload-queue`.
 * Phase 9: offline local recovery + drain unique works.
 */
object DinamicWorkScheduler {
  private const val TAG = "DinamicWorkScheduler"

  fun schedule(context: Context, name: String, tag: String) {
    Log.i(TAG, "schedule name=$name tag=$tag")
    when (name) {
      OfflineOpsLocalRecoveryWorker.UNIQUE_NAME,
      "dinamic-offline-local-recovery",
      -> {
        OfflineOpsLocalRecoveryWorker.schedule(context, expedited = tag == "expedited")
        return
      }
      OfflineOpsDrainWorker.UNIQUE_NAME,
      "dinamic-offline-operations",
      OfflineOpsRecoveryWorker.UNIQUE_NAME,
      -> {
        // Drain requires network; also kick local recovery (no network).
        OfflineOpsLocalRecoveryWorker.schedule(context, expedited = false)
        OfflineOpsDrainWorker.schedule(context, expedited = tag == "expedited")
        return
      }
    }
    Log.i(TAG, "schedule → global upload queue")
    DinamicUploadWorker.scheduleQueue(context)
  }

  fun cancel(context: Context, name: String) {
    Log.i(TAG, "cancel name=$name")
    when {
      name == UploadContracts.UNIQUE_QUEUE_NAME || name == "dinamic-upload-queue" -> {
        DinamicUploadWorker.cancelAll(context)
      }
      name.startsWith("dinamic-upload-session-") || name.startsWith("upload-session-") -> {
        DinamicUploadWorker.cancelAll(context)
      }
      else -> {
        WorkManagerCancelByName(context, name)
      }
    }
  }

  fun cancelAll(context: Context) {
    DinamicUploadWorker.cancelAll(context)
  }

  private fun WorkManagerCancelByName(context: Context, name: String) {
    androidx.work.WorkManager.getInstance(context).cancelUniqueWork(name)
  }
}
