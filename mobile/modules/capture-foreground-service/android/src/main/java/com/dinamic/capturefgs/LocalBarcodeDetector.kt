package com.dinamic.capturefgs

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.barcode.BarcodeScanner
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

/**
 * Offline ML Kit barcode detection for Phase 3 shadow CODE_SCAN.
 * - At most one in-flight ML Kit operation (mutex).
 * - Bitmap kept alive until Task settles; closed via [LoadedScanImage.close].
 * - No CountDownLatch; cancellable coroutine timeout owns the operation.
 */
object LocalBarcodeDetector {
  const val TIMEOUT_MS = 8_000L

  private val formatMap = mapOf(
    "QR_CODE" to Barcode.FORMAT_QR_CODE,
    "CODE_128" to Barcode.FORMAT_CODE_128,
    "CODE_39" to Barcode.FORMAT_CODE_39,
    "EAN_13" to Barcode.FORMAT_EAN_13,
    "EAN_8" to Barcode.FORMAT_EAN_8,
    "UPC_A" to Barcode.FORMAT_UPC_A,
    "UPC_E" to Barcode.FORMAT_UPC_E,
  )

  private val reverseFormat = mapOf(
    Barcode.FORMAT_QR_CODE to "QR_CODE",
    Barcode.FORMAT_CODE_128 to "CODE_128",
    Barcode.FORMAT_CODE_39 to "CODE_39",
    Barcode.FORMAT_EAN_13 to "EAN_13",
    Barcode.FORMAT_EAN_8 to "EAN_8",
    Barcode.FORMAT_UPC_A to "UPC_A",
    Barcode.FORMAT_UPC_E to "UPC_E",
  )

  private val scanMutex = Mutex()
  private val activeScanner = AtomicReference<BarcodeScanner?>(null)

  data class LoadedScanImage(
    val inputImage: InputImage,
    val close: () -> Unit,
  )

  fun isAvailable(): Boolean {
    return try {
      BarcodeScanning.getClient()
      true
    } catch (_: Throwable) {
      false
    }
  }

  /**
   * Suspendable detect. Throws typed codes:
   * LOCAL_SCAN_TIMEOUT | LOCAL_SCAN_CANCELLED | LOCAL_SCAN_FILE_UNREADABLE |
   * LOCAL_SCAN_DECODE_FAILED | LOCAL_SCAN_BUSY | barcode_scan_failed
   */
  suspend fun detect(
    context: Context,
    uriString: String,
    formatsCsv: String,
    timeoutMs: Long = TIMEOUT_MS,
    forceBitmapFallback: Boolean = false,
  ): List<Map<String, String>> = withContext(Dispatchers.IO) {
    if (!scanMutex.tryLock()) {
      throw Exception("LOCAL_SCAN_BUSY")
    }
    var loaded: LoadedScanImage? = null
    var scanner: BarcodeScanner? = null
    try {
      loaded = loadScanImage(context, uriString, forceBitmapFallback)
      scanner = BarcodeScanning.getClient(buildOptions(formatsCsv))
      activeScanner.set(scanner)
      try {
        withTimeout(timeoutMs) {
          awaitBarcodes(scanner!!, loaded!!.inputImage)
        }
      } catch (e: TimeoutCancellationException) {
        throw Exception("LOCAL_SCAN_TIMEOUT")
      }
    } finally {
      activeScanner.compareAndSet(scanner, null)
      try {
        scanner?.close()
      } catch (_: Throwable) {
      }
      try {
        loaded?.close?.invoke()
      } catch (_: Throwable) {
      }
      scanMutex.unlock()
    }
  }

  /** Test / diagnostics: load image without running ML Kit. Caller must close. */
  fun loadScanImageForTest(
    context: Context,
    uriString: String,
    forceBitmapFallback: Boolean,
  ): LoadedScanImage = loadScanImage(context, uriString, forceBitmapFallback)

  private fun buildOptions(formatsCsv: String): BarcodeScannerOptions {
    val formats = parseFormats(formatsCsv)
    val optionsBuilder = BarcodeScannerOptions.Builder()
    if (formats.isEmpty()) {
      optionsBuilder.setBarcodeFormats(
        Barcode.FORMAT_QR_CODE,
        Barcode.FORMAT_CODE_128,
        Barcode.FORMAT_CODE_39,
        Barcode.FORMAT_EAN_13,
        Barcode.FORMAT_EAN_8,
        Barcode.FORMAT_UPC_A,
        Barcode.FORMAT_UPC_E,
      )
    } else {
      val first = formats.first()
      val rest = formats.drop(1).toIntArray()
      optionsBuilder.setBarcodeFormats(first, *rest)
    }
    return optionsBuilder.build()
  }

  private suspend fun awaitBarcodes(
    scanner: BarcodeScanner,
    image: InputImage,
  ): List<Map<String, String>> = suspendCancellableCoroutine { cont ->
    val settled = AtomicBoolean(false)
    val task: Task<List<Barcode>> = scanner.process(image)

    cont.invokeOnCancellation {
      if (settled.compareAndSet(false, true)) {
        // Best-effort: close scanner so the Task is abandoned; late callbacks ignored.
        try {
          scanner.close()
        } catch (_: Throwable) {
        }
      }
    }

    task
      .addOnSuccessListener { barcodes ->
        if (!settled.compareAndSet(false, true)) {
          return@addOnSuccessListener
        }
        if (!cont.isActive) {
          return@addOnSuccessListener
        }
        cont.resume(
          barcodes.mapNotNull { barcode ->
            val raw = barcode.rawValue?.trim().orEmpty()
            if (raw.isEmpty()) {
              null
            } else {
              mapOf(
                "rawValue" to raw.take(512),
                "format" to (reverseFormat[barcode.format] ?: "UNKNOWN"),
              )
            }
          },
        )
      }
      .addOnFailureListener { e ->
        if (!settled.compareAndSet(false, true)) {
          return@addOnFailureListener
        }
        if (!cont.isActive) {
          return@addOnFailureListener
        }
        cont.resumeWithException(Exception(e.message ?: "barcode_scan_failed", e))
      }
      .addOnCanceledListener {
        if (!settled.compareAndSet(false, true)) {
          return@addOnCanceledListener
        }
        if (!cont.isActive) {
          return@addOnCanceledListener
        }
        cont.resumeWithException(Exception("LOCAL_SCAN_CANCELLED"))
      }
  }

  private fun parseFormats(formatsCsv: String): List<Int> {
    return formatsCsv
      .split(',')
      .map { it.trim().uppercase() }
      .mapNotNull { formatMap[it] }
      .distinct()
  }

  private fun loadScanImage(
    context: Context,
    uriString: String,
    forceBitmapFallback: Boolean,
  ): LoadedScanImage {
    val cleaned = uriString.removePrefix("file://")
    val file = File(cleaned)
    if (!file.exists() || !file.canRead()) {
      throw Exception("LOCAL_SCAN_FILE_UNREADABLE")
    }

    if (!forceBitmapFallback) {
      try {
        val image = InputImage.fromFilePath(context, Uri.fromFile(file))
        return LoadedScanImage(inputImage = image, close = {})
      } catch (_: Throwable) {
        // fall through to bitmap
      }
    }

    val bitmap = BitmapFactory.decodeFile(file.absolutePath)
      ?: throw Exception("LOCAL_SCAN_DECODE_FAILED")
    val image = InputImage.fromBitmap(bitmap, 0)
    val closed = AtomicBoolean(false)
    return LoadedScanImage(
      inputImage = image,
      close = {
        if (closed.compareAndSet(false, true) && !bitmap.isRecycled) {
          bitmap.recycle()
        }
      },
    )
  }
}
