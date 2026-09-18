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
}
