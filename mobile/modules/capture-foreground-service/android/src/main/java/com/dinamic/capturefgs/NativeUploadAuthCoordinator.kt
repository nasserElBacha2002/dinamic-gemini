package com.dinamic.capturefgs

import android.content.Context
import android.util.Log

/**
 * Ensures vault availability and refreshes access tokens for the native worker.
 */
class NativeUploadAuthCoordinator(
  private val context: Context,
  private val uploaderFactory: (apiBaseUrl: String, apiKey: String?) -> MultipartUploader =
    { base, key -> MultipartUploader(base, key) },
) {
  data class AuthSession(
    val apiBaseUrl: String,
    val apiKey: String?,
    var accessToken: String,
    val refreshToken: String?,
  )

  sealed class ResolveResult {
    data class Ready(val session: AuthSession) : ResolveResult()
    data class Blocked(val code: String) : ResolveResult()
  }

  fun resolve(): ResolveResult {
    val auth = AuthVault.read(context)
    if (!auth.available) {
      return ResolveResult.Blocked(UploadContracts.CODE_AUTH_VAULT_UNAVAILABLE)
    }
    if (!auth.workerEnabled) {
      return ResolveResult.Blocked("WORKER_DISABLED")
    }
    if (auth.queuePaused) {
      return ResolveResult.Blocked(UploadContracts.CODE_QUEUE_PAUSED)
    }
    if (auth.apiBaseUrl.isNullOrBlank()) {
      return ResolveResult.Blocked("API_BASE_MISSING")
    }
    val access = auth.accessToken
    if (access.isNullOrBlank()) {
      return ResolveResult.Blocked(UploadContracts.CODE_AUTH_REQUIRED)
    }
    return ResolveResult.Ready(
      AuthSession(
        apiBaseUrl = auth.apiBaseUrl,
        apiKey = auth.apiKey,
        accessToken = access,
        refreshToken = auth.refreshToken,
      ),
    )
  }

  fun refresh(session: AuthSession): Boolean {
    val refresh = session.refreshToken
    if (refresh.isNullOrBlank()) {
      Log.w(TAG, "refresh skipped — no refresh token")
      return false
    }
    val uploader = uploaderFactory(session.apiBaseUrl, session.apiKey)
    val result = uploader.refreshAccessToken(refresh)
    if (result.accessToken.isNullOrBlank()) {
      Log.w(TAG, "refresh failed: ${result.errorCode}")
      return false
    }
    if (!AuthVault.saveAccessToken(context, result.accessToken)) {
      Log.e(TAG, "failed to persist refreshed access token")
      return false
    }
    session.accessToken = result.accessToken
    return true
  }

  companion object {
    private const val TAG = "NativeUploadAuth"
  }
}
