package com.dinamic.capturefgs

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class CaptureForegroundModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("CaptureForegroundService")

    AsyncFunction("startService") { title: String, body: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot start foreground service")
      CaptureForegroundService.start(context, title, body)
    }

    AsyncFunction("updateNotification") { title: String, body: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot update notification")
      CaptureForegroundService.update(context, title, body)
    }

    AsyncFunction("stopService") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot stop foreground service")
      CaptureForegroundService.stop(context)
    }

    AsyncFunction("scheduleUniqueWork") { name: String, tag: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot schedule work")
      DinamicWorkScheduler.schedule(context, name, tag)
    }

    AsyncFunction("cancelUniqueWork") { name: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot cancel work")
      DinamicWorkScheduler.cancel(context, name)
    }

    AsyncFunction("cancelAllUploadWork") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot cancel work")
      DinamicWorkScheduler.cancelAll(context)
    }

    AsyncFunction("pauseUploadQueue") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot pause queue")
      DinamicUploadWorker.pauseQueue(context)
    }

    AsyncFunction("resumeUploadQueue") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot resume queue")
      DinamicUploadWorker.resumeQueue(context)
    }

    /**
     * Persist vault with commit(). Returns false if encrypted vault unavailable or commit fails.
     * Callers must not schedule WorkManager until this returns true.
     */
    AsyncFunction("syncUploadAuth") { params: Map<String, Any?> ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot sync auth")
      val previous = AuthVault.read(context)
      val allowMobileData = (params["allowMobileData"] as? Boolean) ?: true
      val workerEnabled = (params["workerEnabled"] as? Boolean) ?: false
      val rebootResume = (params["rebootResume"] as? Boolean) ?: false
      val ok = AuthVault.sync(
        context = context,
        accessToken = params["accessToken"] as? String,
        refreshToken = params["refreshToken"] as? String,
        apiBaseUrl = params["apiBaseUrl"] as? String,
        apiKey = params["apiKey"] as? String,
        allowMobileData = allowMobileData,
        fgsEnabled = (params["fgsEnabled"] as? Boolean) ?: false,
        workerEnabled = workerEnabled,
        rebootResume = rebootResume,
        sqliteDbPath = params["sqliteDbPath"] as? String,
      )
      if (!ok) {
        return@AsyncFunction false
      }
      if (!workerEnabled || !rebootResume) {
        // Prefer explicit cancel when flags turn off; boot receiver also enforces rebootResume.
        if (!workerEnabled) {
          DinamicUploadWorker.cancelAll(context)
        }
      }
      val cellularChanged =
        previous.available && previous.allowMobileData != allowMobileData
      if (cellularChanged && workerEnabled) {
        DinamicUploadWorker.scheduleQueue(context, replace = true)
      }
      true
    }

    AsyncFunction("clearUploadAuth") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot clear auth")
      AuthVault.clearAll(context)
      DinamicUploadWorker.cancelAll(context)
    }

    AsyncFunction("getBackgroundUploadStatus") {
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot read status")
      DinamicUploadWorker.statusSummary(context)
    }

    AsyncFunction("scheduleUploadQueue") { expedited: Boolean? ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot schedule queue")
      val auth = AuthVault.read(context)
      if (!auth.available) {
        throw Exception(UploadContracts.CODE_AUTH_VAULT_UNAVAILABLE)
      }
      DinamicUploadWorker.scheduleQueue(context, expedited == true)
    }

    AsyncFunction("isBarcodeScannerAvailable") {
      LocalBarcodeDetector.isAvailable()
    }

    AsyncFunction("detectBarcodes") { uri: String, formatsCsv: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot scan barcodes")
      LocalBarcodeDetector.detect(context, uri, formatsCsv)
    }
  }
}
