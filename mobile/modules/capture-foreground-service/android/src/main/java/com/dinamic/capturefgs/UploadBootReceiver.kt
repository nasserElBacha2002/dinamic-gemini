package com.dinamic.capturefgs

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * After device reboot: if rebootResume is false, cancel persisted upload work.
 * When true, WorkManager reschedules automatically — no action.
 */
class UploadBootReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent?) {
    if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
    val auth = AuthVault.read(context)
    if (!auth.available) {
      Log.w(TAG, "boot: vault unavailable — cancel upload work")
      DinamicUploadWorker.cancelAll(context)
      return
    }
    if (!auth.rebootResume || !auth.workerEnabled) {
      Log.i(TAG, "boot: rebootResume/worker off — cancel persisted upload work")
      DinamicUploadWorker.cancelAll(context)
    }
  }

  companion object {
    private const val TAG = "UploadBootReceiver"
  }
}
