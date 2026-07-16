package com.dinamic.capturefgs

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

/**
 * Foreground Service used while a capture session is active (Fase 0 spike).
 * Type: dataSync — progressive gallery observation + upload preparation.
 */
class CaptureForegroundService : Service() {
  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    when (intent?.action) {
      ACTION_STOP -> {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        return START_NOT_STICKY
      }
      ACTION_UPDATE -> {
        val title = intent.getStringExtra(EXTRA_TITLE) ?: "Captura activa"
        val body = intent.getStringExtra(EXTRA_BODY) ?: ""
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIFICATION_ID, buildNotification(title, body))
        return START_STICKY
      }
      else -> {
        val title = intent?.getStringExtra(EXTRA_TITLE) ?: "Captura activa"
        val body = intent?.getStringExtra(EXTRA_BODY) ?: ""
        ensureChannel()
        val notification = buildNotification(title, body)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
          startForeground(
            NOTIFICATION_ID,
            notification,
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
          )
        } else {
          startForeground(NOTIFICATION_ID, notification)
        }
        return START_STICKY
      }
    }
  }

  private fun ensureChannel() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    val channel = NotificationChannel(
      CHANNEL_ID,
      "Captura de inventario",
      NotificationManager.IMPORTANCE_LOW,
    ).apply {
      description = "Mantiene la detección de fotografías activa durante la captura"
      setShowBadge(false)
    }
    nm.createNotificationChannel(channel)
  }

  private fun buildNotification(title: String, body: String): Notification {
    val launch = packageManager.getLaunchIntentForPackage(packageName)
    val pending = PendingIntent.getActivity(
      this,
      0,
      launch,
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    return NotificationCompat.Builder(this, CHANNEL_ID)
      .setContentTitle(title)
      .setContentText(body)
      .setSmallIcon(android.R.drawable.ic_menu_camera)
      .setOngoing(true)
      .setOnlyAlertOnce(true)
      .setContentIntent(pending)
      .setCategory(NotificationCompat.CATEGORY_SERVICE)
      .build()
  }

  companion object {
    const val CHANNEL_ID = "dinamic_capture_fgs"
    const val NOTIFICATION_ID = 42001
    const val ACTION_START = "com.dinamic.capturefgs.START"
    const val ACTION_UPDATE = "com.dinamic.capturefgs.UPDATE"
    const val ACTION_STOP = "com.dinamic.capturefgs.STOP"
    const val EXTRA_TITLE = "title"
    const val EXTRA_BODY = "body"

    fun start(context: Context, title: String, body: String) {
      val intent = Intent(context, CaptureForegroundService::class.java).apply {
        action = ACTION_START
        putExtra(EXTRA_TITLE, title)
        putExtra(EXTRA_BODY, body)
      }
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
      } else {
        context.startService(intent)
      }
    }

    fun update(context: Context, title: String, body: String) {
      val intent = Intent(context, CaptureForegroundService::class.java).apply {
        action = ACTION_UPDATE
        putExtra(EXTRA_TITLE, title)
        putExtra(EXTRA_BODY, body)
      }
      context.startService(intent)
    }

    fun stop(context: Context) {
      val intent = Intent(context, CaptureForegroundService::class.java).apply {
        action = ACTION_STOP
      }
      context.startService(intent)
    }
  }
}
