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

    // Minimal unique-work bridge (Fase 3). Schedules a no-op wake so JS restore can drain
    // SQLite-backed queues after process death. Full HTTP WorkManager is a follow-up.
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
  }
}
