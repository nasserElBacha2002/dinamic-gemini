package com.dinamic.capturefgs

import android.content.Context
import android.util.Log

/**
 * Phase 2: single unique WorkManager queue `dinamic-upload-queue`.
 * Session-named work is mapped to the global queue (no duplicate workers).
 */
object DinamicWorkScheduler {
  private const val TAG = "DinamicWorkScheduler"

  fun schedule(context: Context, name: String, tag: String) {
    Log.i(TAG, "schedule name=$name tag=$tag → global queue")
    DinamicUploadWorker.scheduleQueue(context)
  }

  fun cancel(context: Context, name: String) {
    Log.i(TAG, "cancel name=$name")
    when {
      name == UploadContracts.UNIQUE_QUEUE_NAME || name == "dinamic-upload-queue" -> {
        // Cancel WorkManager only — never sticky-pause AuthVault.
        // Pause is reserved for the notification "Pausar cola" action.
        DinamicUploadWorker.cancelAll(context)
      }
      name.startsWith("dinamic-upload-session-") || name.startsWith("upload-session-") -> {
        // Session cancel maps to the shared queue; cancel work without pausing.
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
