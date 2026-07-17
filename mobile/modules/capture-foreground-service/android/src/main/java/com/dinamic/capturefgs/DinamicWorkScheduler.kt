package com.dinamic.capturefgs

import android.content.Context
import android.util.Log
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters

/**
 * Unique WorkManager entries that wake the process so JS can restore SQLite queues.
 * Does not perform HTTP uploads itself (ownership remains in JS UploadQueue / JobMonitor).
 */
object DinamicWorkScheduler {
  private const val TAG = "DinamicWorkScheduler"

  fun schedule(context: Context, name: String, tag: String) {
    val request = OneTimeWorkRequestBuilder<WakeDrainWorker>()
      .addTag(tag)
      .build()
    WorkManager.getInstance(context.applicationContext)
      .enqueueUniqueWork(name, ExistingWorkPolicy.KEEP, request)
    Log.i(TAG, "scheduled unique work name=$name tag=$tag")
  }

  fun cancel(context: Context, name: String) {
    WorkManager.getInstance(context.applicationContext).cancelUniqueWork(name)
    Log.i(TAG, "cancelled unique work name=$name")
  }
}

class WakeDrainWorker(
  context: Context,
  params: WorkerParameters,
) : Worker(context, params) {
  override fun doWork(): Result {
    // No-op: SQLite is source of truth; JS drains on next app open / FGS.
    return Result.success()
  }
}
