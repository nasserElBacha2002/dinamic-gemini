package com.dinamic.capturefgs

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Notification action: pause the upload queue (cancel WorkManager + OkHttp + persist PAUSED).
 */
class UploadPauseReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent?) {
    if (intent?.action != ACTION_PAUSE_QUEUE) return
    Log.i(TAG, "user paused upload queue from notification")
    AuthVault.setQueuePaused(context, true)
    ActiveUploadRegistry.cancelActive()
    DinamicUploadWorker.pauseQueue(context)
  }

  companion object {
    private const val TAG = "UploadPauseReceiver"
    const val ACTION_PAUSE_QUEUE = "com.dinamic.capturefgs.ACTION_PAUSE_UPLOAD_QUEUE"
  }
}
