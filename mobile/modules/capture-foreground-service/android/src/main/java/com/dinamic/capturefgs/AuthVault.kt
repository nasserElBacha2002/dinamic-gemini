package com.dinamic.capturefgs

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Encrypted-only mirror of JS SecureStore tokens + API config for native upload worker.
 * Never falls back to plaintext SharedPreferences.
 */
object AuthVault {
  private const val TAG = "AuthVault"
  private const val PREFS = "dinamic_upload_auth_vault"
  private const val KEY_ACCESS = "access_token"
  private const val KEY_REFRESH = "refresh_token"
  private const val KEY_API_BASE = "api_base_url"
  private const val KEY_API_KEY = "api_key"
  private const val KEY_ALLOW_CELLULAR = "allow_mobile_data"
  private const val KEY_FGS_ENABLED = "fgs_enabled"
  private const val KEY_WORKER_ENABLED = "worker_enabled"
  private const val KEY_REBOOT_RESUME = "reboot_resume"
  private const val KEY_QUEUE_PAUSED = "queue_paused"
  private const val KEY_DB_PATH = "sqlite_db_path"

  const val ERROR_VAULT_UNAVAILABLE = "AUTH_VAULT_UNAVAILABLE"

  data class Snapshot(
    val available: Boolean,
    val accessToken: String?,
    val refreshToken: String?,
    val apiBaseUrl: String?,
    val apiKey: String?,
    val allowMobileData: Boolean,
    val fgsEnabled: Boolean,
    val workerEnabled: Boolean,
    val rebootResume: Boolean,
    val queuePaused: Boolean,
    val sqliteDbPath: String?,
    val errorCode: String? = null,
  )

  @Volatile
  private var cachedPrefs: SharedPreferences? = null

  @Volatile
  private var vaultUnavailable = false

  fun isAvailable(context: Context): Boolean {
    if (vaultUnavailable) return false
    return encryptedPrefs(context) != null
  }

  private fun encryptedPrefs(context: Context): SharedPreferences? {
    cachedPrefs?.let { return it }
    if (vaultUnavailable) return null
    return try {
      val masterKey = MasterKey.Builder(context.applicationContext)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
      EncryptedSharedPreferences.create(
        context.applicationContext,
        PREFS,
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
      ).also { cachedPrefs = it }
    } catch (e: Exception) {
      vaultUnavailable = true
      cachedPrefs = null
      Log.e(TAG, "EncryptedSharedPreferences unavailable: ${e.javaClass.simpleName}")
      null
    }
  }

  /**
   * Persist critical config with commit(). Returns false if vault unavailable or commit fails.
   * Callers must not schedule WorkManager until this returns true.
   */
  fun sync(
    context: Context,
    accessToken: String?,
    refreshToken: String?,
    apiBaseUrl: String?,
    apiKey: String?,
    allowMobileData: Boolean,
    fgsEnabled: Boolean,
    workerEnabled: Boolean,
    rebootResume: Boolean,
    sqliteDbPath: String? = null,
  ): Boolean {
    val prefs = encryptedPrefs(context) ?: return false
    val editor = prefs.edit()
      .putString(KEY_ACCESS, accessToken)
      .putString(KEY_REFRESH, refreshToken)
      .putString(KEY_API_BASE, apiBaseUrl)
      .putString(KEY_API_KEY, apiKey)
      .putBoolean(KEY_ALLOW_CELLULAR, allowMobileData)
      .putBoolean(KEY_FGS_ENABLED, fgsEnabled)
      .putBoolean(KEY_WORKER_ENABLED, workerEnabled)
      .putBoolean(KEY_REBOOT_RESUME, rebootResume)
    if (sqliteDbPath != null) {
      editor.putString(KEY_DB_PATH, sqliteDbPath)
    }
    return editor.commit()
  }

  fun setQueuePaused(context: Context, paused: Boolean): Boolean {
    val prefs = encryptedPrefs(context) ?: return false
    return prefs.edit().putBoolean(KEY_QUEUE_PAUSED, paused).commit()
  }

  fun clearTokens(context: Context): Boolean {
    val prefs = encryptedPrefs(context) ?: return false
    return prefs.edit()
      .remove(KEY_ACCESS)
      .remove(KEY_REFRESH)
      .commit()
  }

  fun clearAll(context: Context): Boolean {
    val prefs = encryptedPrefs(context) ?: return false
    cachedPrefs = null
    return prefs.edit().clear().commit()
  }

  fun read(context: Context): Snapshot {
    val prefs = encryptedPrefs(context)
    if (prefs == null) {
      return Snapshot(
        available = false,
        accessToken = null,
        refreshToken = null,
        apiBaseUrl = null,
        apiKey = null,
        allowMobileData = true,
        fgsEnabled = false,
        workerEnabled = false,
        rebootResume = false,
        queuePaused = false,
        sqliteDbPath = null,
        errorCode = ERROR_VAULT_UNAVAILABLE,
      )
    }
    return Snapshot(
      available = true,
      accessToken = prefs.getString(KEY_ACCESS, null),
      refreshToken = prefs.getString(KEY_REFRESH, null),
      apiBaseUrl = prefs.getString(KEY_API_BASE, null),
      apiKey = prefs.getString(KEY_API_KEY, null),
      allowMobileData = prefs.getBoolean(KEY_ALLOW_CELLULAR, true),
      fgsEnabled = prefs.getBoolean(KEY_FGS_ENABLED, false),
      workerEnabled = prefs.getBoolean(KEY_WORKER_ENABLED, false),
      rebootResume = prefs.getBoolean(KEY_REBOOT_RESUME, false),
      queuePaused = prefs.getBoolean(KEY_QUEUE_PAUSED, false),
      sqliteDbPath = prefs.getString(KEY_DB_PATH, null),
      errorCode = null,
    )
  }

  fun saveAccessToken(context: Context, accessToken: String): Boolean {
    val prefs = encryptedPrefs(context) ?: return false
    return prefs.edit().putString(KEY_ACCESS, accessToken).commit()
  }

  /** Test-only: reset in-memory failure latch. */
  internal fun resetAvailabilityForTests() {
    vaultUnavailable = false
    cachedPrefs = null
  }
}
