package com.dinamic.capturefgs

import android.content.Context
import android.util.Log

/**
 * Honest background policy (Fase 3 correction):
 * Native WorkManager HTTP drain is NOT implemented. Scheduling is a no-op so we do not
 * pretend uploads continue after process death.
 *
 * Recovery happens when the app is opened again (SQLite restore + JS UploadQueue / JobMonitor).
 * Foreground Service still covers active capture while the process is alive.
 */
object DinamicWorkScheduler {
  private const val TAG = "DinamicWorkScheduler"

  fun schedule(context: Context, name: String, tag: String) {
    Log.i(TAG, "schedule ignored (no native upload worker): name=$name tag=$tag")
  }

  fun cancel(context: Context, name: String) {
    Log.i(TAG, "cancel ignored (no native upload worker): name=$name")
  }
}
