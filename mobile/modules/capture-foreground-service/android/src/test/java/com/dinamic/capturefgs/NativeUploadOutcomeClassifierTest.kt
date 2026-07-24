package com.dinamic.capturefgs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeUploadOutcomeClassifierTest {
  @Test
  fun `413 maps to reprepare required`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(
        httpStatus = 413,
        uploaded = emptyList(),
        errors = emptyList(),
        rawErrorCode = UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED,
        rawMessage = "too large",
      ),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.REPREPARE_REQUIRED, c.kind)
    assertEquals(UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED, c.code)
  }

  @Test
  fun `timeout is retryable`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(0, emptyList(), emptyList(), UploadContracts.CODE_REQUEST_TIMEOUT, "t"),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.RETRYABLE, c.kind)
  }

  @Test
  fun `file missing is permanent`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(0, emptyList(), emptyList(), UploadContracts.CODE_FILE_MISSING, "missing"),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.PERMANENT, c.kind)
  }

  @Test
  fun `cancelled is not retried as network`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(0, emptyList(), emptyList(), UploadContracts.CODE_REQUEST_CANCELLED, "c"),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.CANCELLED, c.kind)
  }

  @Test
  fun `401 is auth required`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(401, emptyList(), emptyList(), null, "unauthorized"),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.AUTH_REQUIRED, c.kind)
  }

  @Test
  fun `500 is retryable`() {
    val c = NativeUploadOutcomeClassifier.classifyHttpBatch(
      MultipartUploader.Result(503, emptyList(), emptyList(), "SERVER_ERROR", "busy"),
    )
    assertEquals(NativeUploadOutcomeClassifier.Kind.RETRYABLE, c.kind)
  }
}

class UploadContractsTest {
  @Test
  fun `paths and multipart fields match TS`() {
    assertEquals("dinamic-upload-queue", UploadContracts.UNIQUE_QUEUE_NAME)
    assertEquals("upload_batch_id", UploadContracts.MULTIPART_FIELD_BATCH)
    assertEquals("client_file_ids", UploadContracts.MULTIPART_FIELD_CLIENT_IDS)
    assertEquals("files", UploadContracts.MULTIPART_FIELD_FILES)
    assertEquals(7, UploadContracts.MIN_SCHEMA_VERSION)
    assertTrue(UploadContracts.LEASE_TTL_MS >= 60_000L)
    val assets = UploadContracts.assetsPath("inv", "aisle")
    assertTrue(assets.contains("/api/v3/inventories/inv/aisles/aisle/assets"))
    val process = UploadContracts.processPath("inv", "aisle")
    assertTrue(process.contains("/process"))
  }

  @Test
  fun `network type helper uses unmetered when cellular disallowed`() {
    assertEquals(
      androidx.work.NetworkType.CONNECTED,
      DinamicUploadWorker.networkTypeFor(true),
    )
    assertEquals(
      androidx.work.NetworkType.UNMETERED,
      DinamicUploadWorker.networkTypeFor(false),
    )
  }
}
