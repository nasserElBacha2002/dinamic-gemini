package com.dinamic.capturefgs

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Rect
import android.util.Log
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
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

/**
 * Offline ML Kit barcode detection for productive CODE_SCAN.
 *
 * Device evidence (aisle edd1b3f6…): multilabel photos returned
 * `raw_codes_detected_count=1` while multiple physical D1 QRs were present.
 * Consolidator/CSV were not the collapse point — ML Kit's single full-frame pass was.
 *
 * Strategy: bitmap decode → full-frame pass → overlapping tiles → zoom crops on
 * potential undecoded boxes → merge unique rawValue.
 */
object LocalBarcodeDetector {
  private const val TAG = "DinamicBarcodeDetect"

  const val TIMEOUT_MS = 20_000L

  private const val SCAN_MAX_EDGE_PX = 2400
  private const val TILE_GRID = 3
  private const val TILE_OVERLAP_FRACTION = 0.20f
  /** Expand potential/undecoded boxes before a zoom re-scan. */
  private const val ZOOM_PAD_FRACTION = 0.35f
  private const val MAX_ZOOM_CROPS = 8

  private val formatMap =
    mapOf(
      "QR_CODE" to Barcode.FORMAT_QR_CODE,
      "CODE_128" to Barcode.FORMAT_CODE_128,
      "CODE_39" to Barcode.FORMAT_CODE_39,
      "EAN_13" to Barcode.FORMAT_EAN_13,
      "EAN_8" to Barcode.FORMAT_EAN_8,
      "UPC_A" to Barcode.FORMAT_UPC_A,
      "UPC_E" to Barcode.FORMAT_UPC_E,
    )

  private val reverseFormat =
    mapOf(
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

  data class TileRect(
    val left: Int,
    val top: Int,
    val width: Int,
    val height: Int,
  )

  private data class ScanPassResult(
    val decoded: List<Map<String, String>>,
    val potentialBoxes: List<Rect>,
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
    @Suppress("UNUSED_PARAMETER") forceBitmapFallback: Boolean = false,
  ): List<Map<String, String>> =
    withContext(Dispatchers.IO) {
      if (!scanMutex.tryLock()) {
        throw Exception("LOCAL_SCAN_BUSY")
      }
      var fullBitmap: Bitmap? = null
      var scanner: BarcodeScanner? = null
      try {
        @Suppress("UNUSED_EXPRESSION")
        context
        val file = resolveReadableFile(uriString)
        fullBitmap = decodeBitmapForScan(file, SCAN_MAX_EDGE_PX)
        scanner = BarcodeScanning.getClient(buildOptions(formatsCsv))
        activeScanner.set(scanner)

        withTimeout(timeoutMs) {
          val bitmap = fullBitmap!!
          val client = scanner!!
          val merged = LinkedHashMap<String, Map<String, String>>()
          val zoomQueue = ArrayList<Rect>()

          val fullPass = scanBitmap(client, bitmap)
          mergeDecoded(merged, fullPass.decoded, 0, 0)
          zoomQueue.addAll(fullPass.potentialBoxes)
          val fullDecoded = merged.size

          val tiles = buildOverlapTiles(bitmap.width, bitmap.height)
          var tileAdds = 0
          for (tile in tiles) {
            val cropped = Bitmap.createBitmap(bitmap, tile.left, tile.top, tile.width, tile.height)
            try {
              val before = merged.size
              val pass = scanBitmap(client, cropped)
              mergeDecoded(merged, pass.decoded, tile.left, tile.top)
              tileAdds += merged.size - before
              for (box in pass.potentialBoxes) {
                zoomQueue.add(
                  Rect(
                    box.left + tile.left,
                    box.top + tile.top,
                    box.right + tile.left,
                    box.bottom + tile.top,
                  ),
                )
              }
            } finally {
              if (!cropped.isRecycled) cropped.recycle()
            }
          }

          var zoomAdds = 0
          val zoomTargets =
            prioritizeZoomTargets(
              imageWidth = bitmap.width,
              imageHeight = bitmap.height,
              candidates = zoomQueue,
              alreadyDecodedBoxes = merged.values.mapNotNull { parseBox(it["boundingBox"]) },
            )
          for (target in zoomTargets.take(MAX_ZOOM_CROPS)) {
            val crop = safeCrop(bitmap, target) ?: continue
            try {
              val before = merged.size
              val pass = scanBitmap(client, crop)
              mergeDecoded(merged, pass.decoded, target.left, target.top)
              zoomAdds += merged.size - before
            } finally {
              if (!crop.isRecycled) crop.recycle()
            }
          }

          Log.i(
            TAG,
            "multipass full=$fullDecoded tile_adds=$tileAdds zoom_adds=$zoomAdds " +
              "merged=${merged.size} image=${bitmap.width}x${bitmap.height} " +
              "tiles=${tiles.size} zooms=${zoomTargets.size.coerceAtMost(MAX_ZOOM_CROPS)}",
          )
          merged.values.toList()
        }
      } catch (e: TimeoutCancellationException) {
        throw Exception("LOCAL_SCAN_TIMEOUT")
      } finally {
        activeScanner.compareAndSet(scanner, null)
        try {
          scanner?.close()
        } catch (_: Throwable) {
        }
        try {
          fullBitmap?.let { if (!it.isRecycled) it.recycle() }
        } catch (_: Throwable) {
        }
        scanMutex.unlock()
      }
    }

  /** Test / diagnostics: load image without running ML Kit. Caller must close. */
  fun loadScanImageForTest(
    @Suppress("UNUSED_PARAMETER") context: Context,
    uriString: String,
    @Suppress("UNUSED_PARAMETER") forceBitmapFallback: Boolean,
  ): LoadedScanImage {
    val file = resolveReadableFile(uriString)
    val bitmap = decodeBitmapForScan(file, SCAN_MAX_EDGE_PX)
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

  /** Visible for unit tests (tile geometry only). */
  fun buildOverlapTiles(width: Int, height: Int): List<TileRect> {
    if (width <= 0 || height <= 0) return emptyList()
    val grid = TILE_GRID
    val overlapX = (width * TILE_OVERLAP_FRACTION).roundToInt().coerceAtLeast(0)
    val overlapY = (height * TILE_OVERLAP_FRACTION).roundToInt().coerceAtLeast(0)
    val cellW = max(1, width / grid)
    val cellH = max(1, height / grid)
    val tiles = ArrayList<TileRect>(grid * grid)
    for (row in 0 until grid) {
      for (col in 0 until grid) {
        val left = if (col == 0) 0 else max(0, col * cellW - overlapX / 2)
        val top = if (row == 0) 0 else max(0, row * cellH - overlapY / 2)
        val right = if (col == grid - 1) width else min(width, (col + 1) * cellW + overlapX / 2)
        val bottom = if (row == grid - 1) height else min(height, (row + 1) * cellH + overlapY / 2)
        val w = (right - left).coerceAtLeast(1)
        val h = (bottom - top).coerceAtLeast(1)
        tiles.add(TileRect(left = left, top = top, width = w, height = h))
      }
    }
    return tiles
  }

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
    optionsBuilder.enableAllPotentialBarcodes()
    return optionsBuilder.build()
  }

  private suspend fun scanBitmap(
    scanner: BarcodeScanner,
    bitmap: Bitmap,
  ): ScanPassResult {
    val image = InputImage.fromBitmap(bitmap, 0)
    return awaitBarcodes(scanner, image)
  }

  private fun mergeDecoded(
    merged: LinkedHashMap<String, Map<String, String>>,
    hits: List<Map<String, String>>,
    offsetX: Int,
    offsetY: Int,
  ) {
    for (hit in hits) {
      val raw = hit["rawValue"]?.trim().orEmpty()
      if (raw.isEmpty()) continue
      if (merged.containsKey(raw)) continue
      val box = hit["boundingBox"].orEmpty()
      val adjustedBox =
        if (box.isNotEmpty() && (offsetX != 0 || offsetY != 0)) {
          shiftBox(box, offsetX, offsetY)
        } else {
          box
        }
      merged[raw] =
        mapOf(
          "rawValue" to raw.take(512),
          "format" to (hit["format"] ?: "UNKNOWN"),
          "boundingBox" to adjustedBox,
        )
    }
  }

  private fun prioritizeZoomTargets(
    imageWidth: Int,
    imageHeight: Int,
    candidates: List<Rect>,
    alreadyDecodedBoxes: List<Rect>,
  ): List<Rect> {
    val padded =
      candidates
        .map { padRect(it, imageWidth, imageHeight, ZOOM_PAD_FRACTION) }
        .filter { it.width() >= 24 && it.height() >= 24 }
        .distinctBy { "${it.left},${it.top},${it.right},${it.bottom}" }
    // Prefer boxes that do not heavily overlap an already-decoded code.
    return padded.sortedByDescending { box ->
      val overlapsDecoded =
        alreadyDecodedBoxes.any { decoded ->
          val inter = Rect(box)
          inter.intersect(decoded)
          inter.width() * inter.height() > 0.5f * box.width() * box.height()
        }
      if (overlapsDecoded) 0 else box.width() * box.height()
    }
  }

  private fun padRect(src: Rect, imageWidth: Int, imageHeight: Int, padFraction: Float): Rect {
    val padX = (src.width() * padFraction).roundToInt().coerceAtLeast(8)
    val padY = (src.height() * padFraction).roundToInt().coerceAtLeast(8)
    return Rect(
      (src.left - padX).coerceAtLeast(0),
      (src.top - padY).coerceAtLeast(0),
      (src.right + padX).coerceAtMost(imageWidth),
      (src.bottom + padY).coerceAtMost(imageHeight),
    )
  }

  private fun safeCrop(bitmap: Bitmap, rect: Rect): Bitmap? {
    val left = rect.left.coerceIn(0, bitmap.width - 1)
    val top = rect.top.coerceIn(0, bitmap.height - 1)
    val width = (rect.right - left).coerceAtLeast(1).coerceAtMost(bitmap.width - left)
    val height = (rect.bottom - top).coerceAtLeast(1).coerceAtMost(bitmap.height - top)
    if (width < 16 || height < 16) return null
    return Bitmap.createBitmap(bitmap, left, top, width, height)
  }

  private fun shiftBox(box: String, offsetX: Int, offsetY: Int): String {
    val parts = box.split(',')
    if (parts.size != 4) return box
    val l = parts[0].toIntOrNull() ?: return box
    val t = parts[1].toIntOrNull() ?: return box
    val w = parts[2].toIntOrNull() ?: return box
    val h = parts[3].toIntOrNull() ?: return box
    return "${l + offsetX},${t + offsetY},$w,$h"
  }

  private fun parseBox(raw: String?): Rect? {
    if (raw.isNullOrBlank()) return null
    val parts = raw.split(',')
    if (parts.size != 4) return null
    val l = parts[0].toIntOrNull() ?: return null
    val t = parts[1].toIntOrNull() ?: return null
    val w = parts[2].toIntOrNull() ?: return null
    val h = parts[3].toIntOrNull() ?: return null
    return Rect(l, t, l + w, t + h)
  }

  private suspend fun awaitBarcodes(
    scanner: BarcodeScanner,
    image: InputImage,
  ): ScanPassResult =
    suspendCancellableCoroutine { cont ->
      val settled = AtomicBoolean(false)
      val task: Task<List<Barcode>> = scanner.process(image)

      cont.invokeOnCancellation {
        if (settled.compareAndSet(false, true)) {
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
          val decoded = ArrayList<Map<String, String>>()
          val potentials = ArrayList<Rect>()
          for (barcode in barcodes) {
            val raw = barcode.rawValue?.trim().orEmpty()
            val box = barcode.boundingBox
            if (raw.isNotEmpty()) {
              val boxStr =
                if (box != null) {
                  "${box.left},${box.top},${box.width()},${box.height()}"
                } else {
                  ""
                }
              decoded.add(
                mapOf(
                  "rawValue" to raw.take(512),
                  "format" to (reverseFormat[barcode.format] ?: "UNKNOWN"),
                  "boundingBox" to boxStr,
                ),
              )
            } else if (box != null) {
              potentials.add(Rect(box))
            }
          }
          cont.resume(ScanPassResult(decoded = decoded, potentialBoxes = potentials))
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

  private fun resolveReadableFile(uriString: String): File {
    val cleaned = uriString.removePrefix("file://")
    val file = File(cleaned)
    if (!file.exists() || !file.canRead()) {
      throw Exception("LOCAL_SCAN_FILE_UNREADABLE")
    }
    return file
  }

  private fun decodeBitmapForScan(file: File, maxEdge: Int): Bitmap {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeFile(file.absolutePath, bounds)
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
      throw Exception("LOCAL_SCAN_DECODE_FAILED")
    }
    var sample = 1
    val longest = max(bounds.outWidth, bounds.outHeight)
    while (longest / sample > maxEdge) {
      sample *= 2
    }
    val opts = BitmapFactory.Options().apply { inSampleSize = sample }
    return BitmapFactory.decodeFile(file.absolutePath, opts)
      ?: throw Exception("LOCAL_SCAN_DECODE_FAILED")
  }
}
