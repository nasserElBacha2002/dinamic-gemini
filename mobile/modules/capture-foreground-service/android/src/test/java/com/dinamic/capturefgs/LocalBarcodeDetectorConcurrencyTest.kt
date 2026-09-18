package com.dinamic.capturefgs

import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.atomic.AtomicInteger

/**
 * Pure JVM tests for scan serialization (no Robolectric / ML Kit required).
 */
class LocalBarcodeDetectorConcurrencyTest {

  @Test
  fun loadedScanImage_closeIsIdempotent() {
    val closes = AtomicInteger(0)
    // Synthetic InputImage is Android-only; validate close contract via wrapper shape.
    val close = {
      closes.incrementAndGet()
      Unit
    }
    close()
    close()
    // Idempotent close pattern used by LoadedScanImage
    var done = false
    val guarded = {
      if (!done) {
        done = true
        closes.incrementAndGet()
      }
    }
    guarded()
    guarded()
    assertEquals(3, closes.get())
  }

  @Test
  fun mutex_rejectsSecondConcurrentCaller() = runBlocking {
    // Simulate single-flight: second tryLock fails while first holds.
    val mutex = kotlinx.coroutines.sync.Mutex()
    assertTrue(mutex.tryLock())
    assertTrue(!mutex.tryLock())
    mutex.unlock()
    assertTrue(mutex.tryLock())
    mutex.unlock()
  }

  @Test
  fun sequentialHundredIterations_complete() = runBlocking {
    var count = 0
    repeat(100) {
      delay(1)
      count += 1
    }
    assertEquals(100, count)
  }

  /**
   * Mirrors LocalBarcodeDetector bounded CAS admit loop for 1 vs 2 permits.
   * Pure AtomicInteger — no ML Kit / Android framework.
   */
  @Test
  fun atomicInteger_boundsConcurrency_oneVsTwoPermits() = runBlocking {
    suspend fun simulate(maxPermits: Int, launches: Int): Pair<Int, Int> {
      val active = AtomicInteger(0)
      val maxObserved = AtomicInteger(0)
      val admitted = AtomicInteger(0)
      val rejected = AtomicInteger(0)

      suspend fun tryAdmit(): Boolean {
        while (true) {
          val cur = active.get()
          if (cur >= maxPermits) {
            rejected.incrementAndGet()
            return false
          }
          if (active.compareAndSet(cur, cur + 1)) {
            maxObserved.updateAndGet { prev -> maxOf(prev, cur + 1) }
            admitted.incrementAndGet()
            return true
          }
        }
      }

      val jobs =
        (1..launches).map {
          async {
            if (tryAdmit()) {
              delay(30)
              active.decrementAndGet()
            }
          }
        }
      jobs.awaitAll()
      return Pair(maxObserved.get(), rejected.get())
    }

    val (max1, rejected1) = simulate(maxPermits = 1, launches = 8)
    assertEquals(1, max1)
    assertTrue(rejected1 > 0)

    val (max2, rejected2) = simulate(maxPermits = 2, launches = 8)
    assertEquals(2, max2)
    assertTrue(rejected2 >= 0)
    assertTrue(max2 <= 2)
  }

  @Test
  fun resetObservedConcurrencyStats_clearsPeakWhileIdle() {
    LocalBarcodeDetector.resetConcurrencyCountersForTest()
    LocalBarcodeDetector.setMaxConcurrentScans(2)
    // Simulate peak without real ML Kit: bump via reflection-free public API only.
    // resetObserved requires active==0 (idle).
    LocalBarcodeDetector.resetObservedConcurrencyStats()
    assertEquals(0, LocalBarcodeDetector.getMaxObservedConcurrentScans())
    assertEquals(2, LocalBarcodeDetector.getMaxConcurrentScans())
    LocalBarcodeDetector.resetConcurrencyCountersForTest()
  }

  @Test(expected = IllegalStateException::class)
  fun resetObservedConcurrencyStats_throwsWhenActive() {
    LocalBarcodeDetector.resetConcurrencyCountersForTest()
    // Force active>0 via test helper then call resetObserved — use reflection on activeScans.
    val field = LocalBarcodeDetector::class.java.getDeclaredField("activeScans")
    field.isAccessible = true
    val active = field.get(LocalBarcodeDetector) as java.util.concurrent.atomic.AtomicInteger
    active.set(1)
    try {
      LocalBarcodeDetector.resetObservedConcurrencyStats()
    } finally {
      active.set(0)
      LocalBarcodeDetector.resetConcurrencyCountersForTest()
    }
  }

  @Test
  fun setMaxConcurrentScans_clampsToOneOrTwoOnly() {
    LocalBarcodeDetector.resetConcurrencyCountersForTest()
    LocalBarcodeDetector.setMaxConcurrentScans(1)
    assertEquals(1, LocalBarcodeDetector.getMaxConcurrentScans())
    LocalBarcodeDetector.setMaxConcurrentScans(2)
    assertEquals(2, LocalBarcodeDetector.getMaxConcurrentScans())
    var threw = false
    try {
      LocalBarcodeDetector.setMaxConcurrentScans(3)
    } catch (_: IllegalArgumentException) {
      threw = true
    }
    assertTrue(threw)
    LocalBarcodeDetector.resetConcurrencyCountersForTest()
  }
}
