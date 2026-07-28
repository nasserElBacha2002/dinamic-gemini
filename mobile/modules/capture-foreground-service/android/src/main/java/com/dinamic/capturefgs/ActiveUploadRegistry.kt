package com.dinamic.capturefgs

import okhttp3.Call
import java.util.concurrent.atomic.AtomicReference

/** Holds the in-flight OkHttp call so notification "Pausar cola" can abort transport. */
object ActiveUploadRegistry {
  private val currentCall = AtomicReference<Call?>(null)

  fun set(call: Call?) {
    currentCall.set(call)
  }

  fun cancelActive() {
    currentCall.getAndSet(null)?.cancel()
  }
}
