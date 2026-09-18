package com.dinamic.capturefgs

import expo.modules.kotlin.functions.Coroutine
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

    /** Phase 4: bound native ML Kit concurrent detects to 1 or 2. */
    AsyncFunction("setBarcodeScanConcurrency") { n: Int ->
      LocalBarcodeDetector.setMaxConcurrentScans(n)
      mapOf(
        "configured" to LocalBarcodeDetector.getMaxConcurrentScans(),
        "active" to LocalBarcodeDetector.getActiveConcurrentScans(),
        "maxObserved" to LocalBarcodeDetector.getMaxObservedConcurrentScans(),
      )
    }

    AsyncFunction("getBarcodeScanConcurrencyStats") {
      mapOf(
        "configured" to LocalBarcodeDetector.getMaxConcurrentScans(),
        "active" to LocalBarcodeDetector.getActiveConcurrentScans(),
        "maxObserved" to LocalBarcodeDetector.getMaxObservedConcurrentScans(),
      )
    }

    /**
     * Clear peak/active counters for a new benchmark arm. Does not change configured concurrency.
     * Must not be called while scans are in flight (active must be 0).
     */
    AsyncFunction("resetBarcodeScanConcurrencyStats") {
      LocalBarcodeDetector.resetObservedConcurrencyStats()
      mapOf(
        "configured" to LocalBarcodeDetector.getMaxConcurrentScans(),
        "active" to LocalBarcodeDetector.getActiveConcurrentScans(),
        "maxObserved" to LocalBarcodeDetector.getMaxObservedConcurrentScans(),
      )
    }

    /**
     * Suspend AsyncFunction (not runBlocking): Expo's modulesQueue is a single
     * HandlerThread; runBlocking held that thread for the whole ML Kit multipass
     * and prevented overlapping detectBarcodes → maxObservedNative stayed 1.
     * Suspend + withContext(IO) inside detect frees the queue so C=2 can overlap.
     */
    AsyncFunction("detectBarcodes") Coroutine { uri: String, formatsCsv: String ->
      val context = appContext.reactContext
        ?: throw Exception("React context unavailable; cannot scan barcodes")
      LocalBarcodeDetector.detect(context, uri, formatsCsv)
    }

    /**
     * Append Base64-decoded bytes to an absolute filesystem path (ZIP streaming).
     * Expo FileSystem cannot append without rewriting the whole file.
     * Native rebuild required when this AsyncFunction is added/changed.
     */
    AsyncFunction("appendBase64File") { absolutePath: String, base64: String ->
      val file = java.io.File(stripFileUri(absolutePath))
      file.parentFile?.mkdirs()
      val bytes = android.util.Base64.decode(base64, android.util.Base64.DEFAULT)
      java.io.FileOutputStream(file, true).use { out ->
        out.write(bytes)
      }
    }

    AsyncFunction("truncateFile") { absolutePath: String ->
      val file = java.io.File(stripFileUri(absolutePath))
      file.parentFile?.mkdirs()
      java.io.FileOutputStream(file, false).use { /* truncate */ }
    }

    /**
     * Append raw bytes from [sourceAbsolutePath] onto [destAbsolutePath] (no Base64).
     * Used for ZIP STORE photo payloads — avoids JS↔native Base64 round-trips.
     * Returns bytes copied.
     */
    AsyncFunction("appendFile") { destAbsolutePath: String, sourceAbsolutePath: String ->
      val dest = java.io.File(stripFileUri(destAbsolutePath))
      val source = java.io.File(stripFileUri(sourceAbsolutePath))
      if (!source.exists() || !source.isFile) {
        throw Exception("source missing: $sourceAbsolutePath (resolved=${source.absolutePath})")
      }
      dest.parentFile?.mkdirs()
      var copied = 0L
      val buf = ByteArray(256 * 1024)
      java.io.FileInputStream(source).use { input ->
        java.io.FileOutputStream(dest, true).use { out ->
          while (true) {
            val n = input.read(buf)
            if (n < 0) break
            out.write(buf, 0, n)
            copied += n.toLong()
          }
        }
      }
      copied.toDouble()
    }

    /**
     * One streaming pass: size + SHA-256 + CRC-32 (ZIP) without loading the file into JS.
     */
    AsyncFunction("digestFile") { absolutePath: String ->
      val file = java.io.File(stripFileUri(absolutePath))
      if (!file.exists() || !file.isFile) {
        throw Exception("file missing: $absolutePath (resolved=${file.absolutePath})")
      }
      val sha = java.security.MessageDigest.getInstance("SHA-256")
      val crc = java.util.zip.CRC32()
      val buf = ByteArray(256 * 1024)
      var size = 0L
      java.io.FileInputStream(file).use { input ->
        while (true) {
          val n = input.read(buf)
          if (n < 0) break
          sha.update(buf, 0, n)
          crc.update(buf, 0, n)
          size += n.toLong()
        }
      }
      mapOf(
        "size" to size.toDouble(),
        "sha256" to sha.digest().joinToString("") { b -> "%02x".format(b) },
        "crc32" to (crc.value and 0xffffffffL).toDouble(),
      )
    }

    AsyncFunction("getFileSize") { absolutePath: String ->
      val file = java.io.File(stripFileUri(absolutePath))
      if (!file.exists() || !file.isFile) {
        throw Exception("file missing: $absolutePath (resolved=${file.absolutePath})")
      }
      file.length().toDouble()
    }

    /**
     * Read [length] bytes at [offset] and return Base64 (bounded ZIP validation).
     * Rejects oversized ranges to protect memory.
     */
    AsyncFunction("readFileRangeBase64") { absolutePath: String, offset: Double, length: Double ->
      val file = java.io.File(stripFileUri(absolutePath))
      if (!file.exists() || !file.isFile) {
        throw Exception("file missing: $absolutePath (resolved=${file.absolutePath})")
      }
      val off = offset.toLong()
      val len = length.toLong()
      if (off < 0 || len < 0 || len > 2L * 1024L * 1024L) {
        throw Exception("invalid range offset=$off length=$len")
      }
      if (off + len > file.length()) {
        throw Exception("range past EOF")
      }
      val buf = ByteArray(len.toInt())
      java.io.RandomAccessFile(file, "r").use { raf ->
        raf.seek(off)
        raf.readFully(buf)
      }
      android.util.Base64.encodeToString(buf, android.util.Base64.NO_WRAP)
    }

    /** Streaming SHA-256 of file contents (does not load whole file). */
    AsyncFunction("hashFileSha256") { absolutePath: String ->
      val file = java.io.File(stripFileUri(absolutePath))
      if (!file.exists() || !file.isFile) {
        throw Exception("file missing: $absolutePath (resolved=${file.absolutePath})")
      }
      val digest = java.security.MessageDigest.getInstance("SHA-256")
      val buf = ByteArray(64 * 1024)
      java.io.FileInputStream(file).use { input ->
        while (true) {
          val n = input.read(buf)
          if (n < 0) break
          digest.update(buf, 0, n)
        }
      }
      digest.digest().joinToString("") { b -> "%02x".format(b) }
    }
  }

  private fun stripFileUri(path: String): String {
    return FileUriPaths.toAbsolutePath(path)
  }
}
