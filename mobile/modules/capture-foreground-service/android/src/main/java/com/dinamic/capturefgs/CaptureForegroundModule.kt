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
  }
}
