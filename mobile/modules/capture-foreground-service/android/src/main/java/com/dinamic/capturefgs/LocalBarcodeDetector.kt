package com.dinamic.capturefgs

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Offline ML Kit barcode detection for Phase 3 shadow CODE_SCAN.
 * Formats limited to the allowlist shared with contracts/code-scan/v1.
 */
object LocalBarcodeDetector {
  private const val TIMEOUT_MS = 8_000L

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

  fun isAvailable(): Boolean {
    return try {
      BarcodeScanning.getClient()
      true
    } catch (_: Throwable) {
      false
    }
  }

  fun detect(context: Context, uriString: String, formatsCsv: String): List<Map<String, String>> {
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
    val scanner = BarcodeScanning.getClient(optionsBuilder.build())
    try {
      val image = loadInputImage(context, uriString)
      val latch = CountDownLatch(1)
      val resultRef = AtomicReference<List<Map<String, String>>>(emptyList())
      val errorRef = AtomicReference<Exception?>(null)

      scanner.process(image)
        .addOnSuccessListener { barcodes ->
          resultRef.set(
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
          latch.countDown()
        }
        .addOnFailureListener { e ->
          errorRef.set(Exception(e.message ?: "barcode_scan_failed", e))
          latch.countDown()
        }

      val completed = latch.await(TIMEOUT_MS, TimeUnit.MILLISECONDS)
      if (!completed) {
        throw Exception("LOCAL_SCAN_TIMEOUT")
      }
      errorRef.get()?.let { throw it }
      return resultRef.get()
    } finally {
      try {
        scanner.close()
      } catch (_: Throwable) {
        // ignore
      }
    }
  }

  private fun parseFormats(formatsCsv: String): List<Int> {
    return formatsCsv
      .split(',')
      .map { it.trim().uppercase() }
      .mapNotNull { formatMap[it] }
      .distinct()
  }

  private fun loadInputImage(context: Context, uriString: String): InputImage {
    val cleaned = uriString.removePrefix("file://")
    val file = File(cleaned)
    if (!file.exists() || !file.canRead()) {
      throw Exception("LOCAL_SCAN_FILE_UNREADABLE")
    }
    return try {
      InputImage.fromFilePath(context, Uri.fromFile(file))
    } catch (_: Throwable) {
      val bitmap = BitmapFactory.decodeFile(file.absolutePath)
        ?: throw Exception("LOCAL_SCAN_DECODE_FAILED")
      try {
        InputImage.fromBitmap(bitmap, 0)
      } finally {
        if (!bitmap.isRecycled) {
          bitmap.recycle()
        }
      }
    }
  }
}
