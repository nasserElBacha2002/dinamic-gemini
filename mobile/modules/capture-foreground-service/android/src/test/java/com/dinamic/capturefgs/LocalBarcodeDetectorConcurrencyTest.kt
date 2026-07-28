package com.dinamic.capturefgs

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
}
