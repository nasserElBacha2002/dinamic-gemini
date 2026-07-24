package com.dinamic.capturefgs

import android.net.Uri
import android.util.Log
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLException

/**
 * Multipart contract must match TS AisleAssetsApi.uploadBatch:
 * - fields: upload_batch_id, client_file_ids (repeated), files (repeated)
 * - headers: Authorization Bearer, optional X-API-Key, Accept application/json
 */
class MultipartUploader(
  private val apiBaseUrl: String,
  private val apiKey: String?,
  private val client: OkHttpClient = defaultClient(),
) {
  data class Result(
    val httpStatus: Int,
    val uploaded: List<UploadSqliteStore.UploadOk>,
    val errors: List<UploadSqliteStore.UploadErr>,
    val rawErrorCode: String?,
    val rawMessage: String?,
  )

  data class ProcessResult(
    val httpStatus: Int,
    val jobId: String?,
    val errorCode: String?,
    val errorMessage: String?,
  )

  data class RefreshResult(
    val accessToken: String?,
    val errorCode: String?,
    val errorMessage: String?,
  )

  fun uploadBatch(
    inventoryId: String,
    aisleId: String,
    uploadBatchId: String,
    photos: List<UploadSqliteStore.EligiblePhoto>,
    accessToken: String,
    /** Invoked on a background timer during the HTTP call. Return false to abort (lost lease). */
    onHeartbeat: (() -> Boolean)? = null,
  ): Result {
    val path = UploadContracts.assetsPath(inventoryId, aisleId)
    val url = apiBaseUrl.trimEnd('/') + path
    val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
    builder.addFormDataPart(UploadContracts.MULTIPART_FIELD_BATCH, uploadBatchId)
    for (p in photos) {
      builder.addFormDataPart(UploadContracts.MULTIPART_FIELD_CLIENT_IDS, p.clientFileId)
    }
    for (p in photos) {
      val fileUri = p.transformUri?.takeIf { it.isNotBlank() } ?: p.uri
      val file = resolveLocalFile(fileUri)
        ?: return Result(
          httpStatus = 0,
          uploaded = emptyList(),
          errors = listOf(
            UploadSqliteStore.UploadErr(
              p.clientFileId,
              UploadContracts.CODE_FILE_MISSING,
              "Archivo local no encontrado",
            ),
          ),
          rawErrorCode = UploadContracts.CODE_FILE_MISSING,
          rawMessage = "Archivo local no encontrado",
        )
      val mime = if (!p.transformUri.isNullOrBlank()) {
        "image/jpeg"
      } else {
        p.mimeType.ifBlank { "image/jpeg" }
      }
      val name = if (!p.transformUri.isNullOrBlank()) {
        p.displayName.replace(Regex("\\.(heic|heif)$", RegexOption.IGNORE_CASE), ".jpg")
      } else {
        p.displayName
      }
      val body = file.asRequestBody(mime.toMediaTypeOrNull() ?: "image/jpeg".toMediaType())
      builder.addFormDataPart(UploadContracts.MULTIPART_FIELD_FILES, name, body)
    }

    val reqBuilder = Request.Builder()
      .url(url)
      .post(builder.build())
      .header("Accept", "application/json")
      .header("Authorization", "Bearer $accessToken")
    if (!apiKey.isNullOrBlank()) {
      reqBuilder.header("X-API-Key", apiKey)
    }

    val call = client.newCall(reqBuilder.build())
    ActiveUploadRegistry.set(call)
    val aborted = AtomicBoolean(false)
    var heartbeatFuture: ScheduledFuture<*>? = null
    val scheduler = if (onHeartbeat != null) {
      Executors.newSingleThreadScheduledExecutor().also { exec ->
        heartbeatFuture = exec.scheduleAtFixedRate(
          {
            try {
              if (!onHeartbeat.invoke()) {
                aborted.set(true)
                call.cancel()
              }
            } catch (e: Exception) {
              Log.w(TAG, "heartbeat failed: ${e.javaClass.simpleName}")
            }
          },
          UploadContracts.HEARTBEAT_INTERVAL_MS,
          UploadContracts.HEARTBEAT_INTERVAL_MS,
          TimeUnit.MILLISECONDS,
        )
      }
    } else {
      null
    }

    return try {
      call.execute().use { resp ->
        if (aborted.get() || call.isCanceled()) {
          return Result(
            httpStatus = 0,
            uploaded = emptyList(),
            errors = emptyList(),
            rawErrorCode = UploadContracts.CODE_REQUEST_CANCELLED,
            rawMessage = "cancelado",
          )
        }
        val text = resp.body?.string().orEmpty()
        parseResponse(resp.code, text)
      }
    } catch (e: Exception) {
      classifyTransport(e, aborted.get() || call.isCanceled())
    } finally {
      heartbeatFuture?.cancel(true)
      scheduler?.shutdownNow()
      ActiveUploadRegistry.set(null)
    }
  }

  fun refreshAccessToken(refreshToken: String): RefreshResult {
    val url = apiBaseUrl.trimEnd('/') + "/auth/refresh"
    val json = JSONObject().put("refresh_token", refreshToken).toString()
    val body = json.toRequestBody("application/json".toMediaType())
    val reqBuilder = Request.Builder()
      .url(url)
      .post(body)
      .header("Accept", "application/json")
    if (!apiKey.isNullOrBlank()) {
      reqBuilder.header("X-API-Key", apiKey)
    }
    return try {
      client.newCall(reqBuilder.build()).execute().use { resp ->
        val text = resp.body?.string().orEmpty()
        if (!resp.isSuccessful) {
          return RefreshResult(
            accessToken = null,
            errorCode = UploadContracts.CODE_AUTH_REQUIRED,
            errorMessage = "refresh HTTP ${resp.code}",
          )
        }
        try {
          val obj = JSONObject(text)
          val token = obj.optString("access_token").takeIf { it.isNotBlank() }
          if (token == null) {
            RefreshResult(null, UploadContracts.CODE_RESPONSE_PARSE_ERROR, "refresh sin access_token")
          } else {
            RefreshResult(token, null, null)
          }
        } catch (e: Exception) {
          RefreshResult(
            null,
            UploadContracts.CODE_RESPONSE_PARSE_ERROR,
            e.message ?: "parse refresh",
          )
        }
      }
    } catch (e: Exception) {
      val classified = classifyTransport(e, false)
      RefreshResult(null, classified.rawErrorCode, classified.rawMessage)
    }
  }

  fun startProcess(
    inventoryId: String,
    aisleId: String,
    idempotencyKey: String,
    identificationMode: String?,
    accessToken: String,
  ): ProcessResult {
    val path = UploadContracts.processPath(inventoryId, aisleId)
    val url = apiBaseUrl.trimEnd('/') + path
    val payload = JSONObject().put("idempotency_key", idempotencyKey)
    val mode = identificationMode?.trim()?.uppercase()
    if (mode == "CODE_SCAN" || mode == "INTERNAL_OCR") {
      payload.put("identification_mode", mode)
    }
    val body = payload.toString().toRequestBody("application/json".toMediaType())
    val reqBuilder = Request.Builder()
      .url(url)
      .post(body)
      .header("Accept", "application/json")
      .header("Authorization", "Bearer $accessToken")
      .header("Idempotency-Key", idempotencyKey)
    if (!apiKey.isNullOrBlank()) {
      reqBuilder.header("X-API-Key", apiKey)
    }
    return try {
      client.newCall(reqBuilder.build()).execute().use { resp ->
        val text = resp.body?.string().orEmpty()
        if (resp.code !in 200..299) {
          return ProcessResult(
            httpStatus = resp.code,
            jobId = null,
            errorCode = extractCode(text) ?: "PROCESS_FAILED",
            errorMessage = extractMessage(text, resp.code),
          )
        }
        try {
          val obj = JSONObject(text)
          val jobId = obj.optString("job_id").takeIf { it.isNotBlank() }
            ?: obj.optJSONObject("job")?.optString("id")?.takeIf { it.isNotBlank() }
          if (jobId == null) {
            ProcessResult(
              resp.code,
              null,
              UploadContracts.CODE_RESPONSE_PARSE_ERROR,
              "process sin job_id",
            )
          } else {
            ProcessResult(resp.code, jobId, null, null)
          }
        } catch (e: Exception) {
          ProcessResult(
            resp.code,
            null,
            UploadContracts.CODE_RESPONSE_PARSE_ERROR,
            e.message ?: "parse process",
          )
        }
      }
    } catch (e: Exception) {
      val classified = classifyTransport(e, false)
      ProcessResult(0, null, classified.rawErrorCode, classified.rawMessage)
    }
  }

  private fun classifyTransport(e: Exception, cancelled: Boolean): Result {
    if (cancelled || e is java.util.concurrent.CancellationException) {
      return Result(0, emptyList(), emptyList(), UploadContracts.CODE_REQUEST_CANCELLED, "cancelado")
    }
    val (code, message) = when (e) {
      is SocketTimeoutException -> UploadContracts.CODE_REQUEST_TIMEOUT to (e.message ?: "timeout")
      is UnknownHostException -> UploadContracts.CODE_NETWORK_ERROR to (e.message ?: "dns")
      is SSLException -> UploadContracts.CODE_TLS_ERROR to (e.message ?: "tls")
      is FileNotFoundException -> UploadContracts.CODE_FILE_MISSING to (e.message ?: "file")
      is IOException -> {
        if (e.message?.contains("Canceled", ignoreCase = true) == true ||
          e.message?.contains("Cancelled", ignoreCase = true) == true
        ) {
          UploadContracts.CODE_REQUEST_CANCELLED to (e.message ?: "cancelado")
        } else {
          UploadContracts.CODE_NETWORK_ERROR to (e.message ?: "io")
        }
      }
      else -> UploadContracts.CODE_NETWORK_ERROR to (e.javaClass.simpleName)
    }
    Log.w(TAG, "upload transport: $code")
    return Result(0, emptyList(), emptyList(), code, message)
  }

  private fun parseResponse(status: Int, text: String): Result {
    if (status !in 200..299) {
      val code = when (status) {
        413 -> UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED
        else -> extractCode(text)
      }
      val message = extractMessage(text, status)
      return Result(
        httpStatus = status,
        uploaded = emptyList(),
        errors = emptyList(),
        rawErrorCode = code,
        rawMessage = message,
      )
    }
    return try {
      val root = JSONObject(text)
      val uploaded = mutableListOf<UploadSqliteStore.UploadOk>()
      val uploadedArr = root.optJSONArray("uploaded")
      if (uploadedArr != null) {
        for (i in 0 until uploadedArr.length()) {
          val item = uploadedArr.getJSONObject(i)
          val cid = item.optString("client_file_id")
          val aid = item.optString("asset_id")
          if (cid.isNotBlank() && aid.isNotBlank()) {
            uploaded.add(UploadSqliteStore.UploadOk(cid, aid))
          }
        }
      }
      val errors = mutableListOf<UploadSqliteStore.UploadErr>()
      val errArr = root.optJSONArray("errors")
      if (errArr != null) {
        for (i in 0 until errArr.length()) {
          val item = errArr.getJSONObject(i)
          errors.add(
            UploadSqliteStore.UploadErr(
              clientFileId = item.optString("client_file_id").ifBlank { null },
              code = item.optString("code").ifBlank { null },
              detail = item.optString("detail").ifBlank { item.optString("message").ifBlank { null } },
            ),
          )
        }
      }
      Result(status, uploaded, errors, null, null)
    } catch (_: Exception) {
      Result(
        status,
        emptyList(),
        emptyList(),
        UploadContracts.CODE_RESPONSE_PARSE_ERROR,
        "Respuesta inválida",
      )
    }
  }

  private fun extractCode(text: String): String? {
    return try {
      val obj = JSONObject(text)
      obj.optString("code").ifBlank {
        obj.optJSONObject("error")?.optString("code")
      }?.ifBlank { null }
    } catch (_: Exception) {
      null
    }
  }

  private fun extractMessage(text: String, status: Int): String {
    return try {
      val obj = JSONObject(text)
      when {
        obj.has("detail") -> obj.get("detail").toString()
        obj.has("message") -> obj.optString("message")
        else -> "HTTP $status"
      }
    } catch (_: Exception) {
      "HTTP $status"
    }
  }

  private fun resolveLocalFile(uri: String): File? {
    val path = when {
      uri.startsWith("file://") -> Uri.parse(uri).path
      uri.startsWith("/") -> uri
      else -> Uri.parse(uri).path
    } ?: return null
    val file = File(path)
    return if (file.exists() && file.canRead() && file.length() > 0) file else null
  }

  companion object {
    private const val TAG = "MultipartUploader"

    fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
      .connectTimeout(30, TimeUnit.SECONDS)
      .readTimeout(120, TimeUnit.SECONDS)
      .writeTimeout(120, TimeUnit.SECONDS)
      .callTimeout(130, TimeUnit.SECONDS)
      .build()
  }
}
