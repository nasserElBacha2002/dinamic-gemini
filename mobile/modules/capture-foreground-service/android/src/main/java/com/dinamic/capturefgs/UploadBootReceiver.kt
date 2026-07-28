package com.dinamic.capturefgs

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * After device reboot: if rebootResume is false, cancel persisted upload work.
 * When true, schedule local offline recovery (no auth required) + drain if vault ok.
 */
class UploadBootReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent?) {
    if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
    // Always attempt local recovery — does not require AuthVault.
    OfflineOpsLocalRecoveryWorker.schedule(context, expedited = false)

    val auth = AuthVault.read(context)
    if (!auth.available) {
      Log.w(TAG, "boot: vault unavailable — local recovery only; cancel upload work")
      DinamicUploadWorker.cancelAll(context)
      return
    }
    if (!auth.rebootResume || !auth.workerEnabled) {
      Log.i(TAG, "boot: rebootResume/worker off — cancel persisted upload work")
      DinamicUploadWorker.cancelAll(context)
      return
    }
    OfflineOpsDrainWorker.schedule(context, expedited = false)
  }

  companion object {
    private const val TAG = "UploadBootReceiver"
  }
}
