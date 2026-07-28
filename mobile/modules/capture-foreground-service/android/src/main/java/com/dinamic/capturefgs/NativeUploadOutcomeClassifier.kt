package com.dinamic.capturefgs

/**
 * Classifies native multipart / process outcomes into durable SQLite actions.
 */
object NativeUploadOutcomeClassifier {
  enum class Kind {
    SUCCESS_PARTIAL,
    REPREPARE_REQUIRED,
    AUTH_REQUIRED,
    RETRYABLE,
    PERMANENT,
    CANCELLED,
  }

  data class Classification(
    val kind: Kind,
    val code: String,
    val message: String,
  )

  fun classifyHttpBatch(result: MultipartUploader.Result): Classification {
    val code = result.rawErrorCode ?: "UPLOAD_FAILED"
    val message = result.rawMessage ?: "error"
    return when {
      result.rawErrorCode == UploadContracts.CODE_REQUEST_CANCELLED ->
        Classification(Kind.CANCELLED, UploadContracts.CODE_REQUEST_CANCELLED, message)
      result.httpStatus == 413 || code == UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED ->
        Classification(
          Kind.REPREPARE_REQUIRED,
          UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED,
          message,
        )
      result.httpStatus == 401 || code == UploadContracts.CODE_AUTH_REQUIRED ->
        Classification(Kind.AUTH_REQUIRED, UploadContracts.CODE_AUTH_REQUIRED, message)
      result.httpStatus == 0 -> when (code) {
        UploadContracts.CODE_REQUEST_TIMEOUT,
        UploadContracts.CODE_NETWORK_ERROR,
        UploadContracts.CODE_TLS_ERROR,
        -> Classification(Kind.RETRYABLE, code, message)
        UploadContracts.CODE_FILE_MISSING ->
          Classification(Kind.PERMANENT, UploadContracts.CODE_FILE_MISSING, message)
        UploadContracts.CODE_RESPONSE_PARSE_ERROR ->
          Classification(Kind.RETRYABLE, UploadContracts.CODE_RESPONSE_PARSE_ERROR, message)
        else -> Classification(Kind.RETRYABLE, code, message)
      }
      result.httpStatus in 400..499 &&
        result.httpStatus != 401 &&
        result.httpStatus != 408 &&
        result.httpStatus != 429 ->
        Classification(Kind.PERMANENT, code, message)
      result.httpStatus >= 500 || result.httpStatus == 408 || result.httpStatus == 429 ->
        Classification(Kind.RETRYABLE, code, message)
      result.httpStatus in 200..299 ->
        Classification(Kind.SUCCESS_PARTIAL, "OK", "ok")
      else -> Classification(Kind.RETRYABLE, code, message)
    }
  }
}
