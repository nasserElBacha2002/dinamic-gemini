package com.dinamic.capturefgs

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * Native durable upload worker. Single unique queue: dinamic-upload-queue.
 * Foreground owned exclusively via CoroutineWorker.setForeground (no duplicate FGS).
 */
class DinamicUploadWorker(
  appContext: Context,
  params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

  override suspend fun doWork(): Result {
    val authCoordinator = NativeUploadAuthCoordinator(applicationContext)
    when (val resolved = authCoordinator.resolve()) {
      is NativeUploadAuthCoordinator.ResolveResult.Blocked -> {
        Log.i(TAG, "worker blocked: ${resolved.code}")
        return when (resolved.code) {
          "WORKER_DISABLED", UploadContracts.CODE_QUEUE_PAUSED -> Result.success(
            workDataOf("error" to resolved.code),
          )
          UploadContracts.CODE_AUTH_VAULT_UNAVAILABLE,
          UploadContracts.CODE_AUTH_REQUIRED,
          -> Result.failure(workDataOf("error" to resolved.code))
          else -> Result.retry()
        }
      }
      is NativeUploadAuthCoordinator.ResolveResult.Ready -> {
        return drain(authCoordinator, resolved.session)
      }
    }
  }

  private suspend fun drain(
    authCoordinator: NativeUploadAuthCoordinator,
    session: NativeUploadAuthCoordinator.AuthSession,
  ): Result {
    val auth = AuthVault.read(applicationContext)
    val store = UploadSqliteStore(applicationContext)
    val open = store.open()
    if (open is UploadSqliteStore.OpenResult.Failed) {
      Log.w(TAG, "db open failed: ${open.code}")
      return if (open.code == UploadContracts.CODE_DB_MIGRATION_REQUIRED) {
        Result.failure(workDataOf("error" to open.code))
      } else {
        Result.retry()
      }
    }
    val db = (open as UploadSqliteStore.OpenResult.Ok).db
    var runSessionIds: Set<String>
    var uploadedThisRun = 0

    return try {
      val now = UploadSqliteStore.nowIso()
      val eligible = store.listEligiblePrepared(db, BATCH_LIMIT, now)
      runSessionIds = eligible.map { it.sessionId }.toSet()

      if (auth.fgsEnabled && eligible.isNotEmpty()) {
        setForeground(
          buildForegroundInfo(
            title = "Subiendo imágenes",
            body = progressText(0, eligible.size, uploadedThisRun),
          ),
        )
      }

      if (eligible.isEmpty()) {
        kickoffProcessIfReady(store, db, session, authCoordinator)
        return Result.success()
      }

      val groups = eligible.groupBy { Triple(it.inventoryId, it.aisleId, it.uploadBatchId) }
      val uploader = MultipartUploader(session.apiBaseUrl, session.apiKey)
      var needsRetry = false
      var authFailed = false
      var reprepareNeeded = false
      var processedInRun = 0

      for ((key, photos) in groups) {
        if (AuthVault.read(applicationContext).queuePaused || isStopped) {
          ActiveUploadRegistry.cancelActive()
          break
        }
        val (inventoryId, aisleId, batchId) = key
        val acquired = mutableListOf<Pair<UploadSqliteStore.EligiblePhoto, String>>()
        for (photo in photos.take(MAX_FILES_PER_REQUEST)) {
          if (store.isCancelRequested(db, photo.id)) continue
          val token = UploadSqliteStore.newLeaseToken()
          val expires = UploadSqliteStore.leaseExpiresIso()
          if (store.tryAcquireLease(
              db,
              photo.id,
              UploadContracts.OWNER_NATIVE,
              token,
              expires,
              UploadSqliteStore.nowIso(),
            )
          ) {
            acquired.add(photo to token)
          }
        }
        if (acquired.isEmpty()) continue

        val live = acquired.filter { (p, token) ->
          if (store.isCancelRequested(db, p.id)) {
            store.markExcludedAfterCancel(db, p.id, token)
            false
          } else {
            true
          }
        }
        if (live.isEmpty()) continue

        fun heartbeatAll(): Boolean {
          val t = UploadSqliteStore.nowIso()
          val exp = UploadSqliteStore.leaseExpiresIso()
          for ((photo, token) in live) {
            if (!store.heartbeatLease(db, photo.id, token, exp, t)) {
              return false
            }
            if (store.isCancelRequested(db, photo.id)) {
              return false
            }
          }
          return !AuthVault.read(applicationContext).queuePaused && !isStopped
        }

        var result = uploader.uploadBatch(
          inventoryId,
          aisleId,
          batchId,
          live.map { it.first },
          session.accessToken,
          onHeartbeat = { heartbeatAll() },
        )

        if (result.httpStatus == 401) {
          if (authCoordinator.refresh(session)) {
            result = uploader.uploadBatch(
              inventoryId,
              aisleId,
              batchId,
              live.map { it.first },
              session.accessToken,
              onHeartbeat = { heartbeatAll() },
            )
          } else {
            authFailed = true
            for ((photo, token) in live) {
              store.markRetryable(
                db,
                photo.id,
                token,
                UploadContracts.CODE_AUTH_REQUIRED,
                "Sesión vencida",
                UploadSqliteStore.nowIso(),
              )
            }
            break
          }
        }

        val classification = NativeUploadOutcomeClassifier.classifyHttpBatch(result)
        when (classification.kind) {
          NativeUploadOutcomeClassifier.Kind.CANCELLED -> {
            for ((photo, token) in live) {
              store.markRetryable(
                db,
                photo.id,
                token,
                UploadContracts.CODE_QUEUE_PAUSED,
                "Cola pausada",
                UploadSqliteStore.nowIso(),
              )
            }
          }
          NativeUploadOutcomeClassifier.Kind.REPREPARE_REQUIRED -> {
            reprepareNeeded = true
            for ((photo, token) in live) {
              store.markReprepareRequired(
                db,
                photo.id,
                token,
                classification.message,
              )
            }
          }
          NativeUploadOutcomeClassifier.Kind.AUTH_REQUIRED -> {
            authFailed = true
            for ((photo, token) in live) {
              store.markRetryable(
                db,
                photo.id,
                token,
                UploadContracts.CODE_AUTH_REQUIRED,
                classification.message,
                UploadSqliteStore.nowIso(),
              )
            }
          }
          NativeUploadOutcomeClassifier.Kind.RETRYABLE -> {
            needsRetry = true
            val next = retryAtIso(live.first().first.uploadAttempts)
            for ((photo, token) in live) {
              store.markRetryable(
                db,
                photo.id,
                token,
                classification.code,
                classification.message,
                next,
              )
            }
          }
          NativeUploadOutcomeClassifier.Kind.PERMANENT -> {
            for ((photo, token) in live) {
              store.markPermanent(
                db,
                photo.id,
                token,
                classification.code,
                classification.message,
              )
            }
          }
          NativeUploadOutcomeClassifier.Kind.SUCCESS_PARTIAL -> {
            val byClient = live.associateBy { it.first.clientFileId }
            val uploadedIds = mutableSetOf<String>()
            for (ok in result.uploaded) {
              val pair = byClient[ok.clientFileId] ?: continue
              if (store.isCancelRequested(db, pair.first.id)) {
                store.markExcludedAfterCancel(db, pair.first.id, pair.second)
                db.execSQL(
                  "UPDATE capture_photos SET backend_asset_id = ?, upload_status = 'remote_delete_pending', updated_at = ? WHERE id = ?",
                  arrayOf(ok.assetId, UploadSqliteStore.nowIso(), pair.first.id),
                )
              } else {
                store.markUploaded(db, pair.first.id, pair.second, ok.assetId, UploadSqliteStore.nowIso())
                uploadedThisRun += 1
              }
              uploadedIds.add(ok.clientFileId)
            }
            for (err in result.errors) {
              val cid = err.clientFileId ?: continue
              val pair = byClient[cid] ?: continue
              uploadedIds.add(cid)
              val next = retryAtIso(pair.first.uploadAttempts)
              store.markRetryable(
                db,
                pair.first.id,
                pair.second,
                err.code ?: "UPLOAD_FAILED",
                err.detail ?: "error",
                next,
              )
              needsRetry = true
            }
            for ((photo, token) in live) {
              if (photo.clientFileId in uploadedIds) continue
              if (store.isCancelRequested(db, photo.id)) {
                store.markExcludedAfterCancel(db, photo.id, token)
                continue
              }
              needsRetry = true
              store.markRetryable(
                db,
                photo.id,
                token,
                "UPLOAD_RESPONSE_INCOMPLETE",
                "El backend no confirmó este archivo",
                retryAtIso(photo.uploadAttempts),
              )
            }
          }
        }

        processedInRun += live.size
        if (auth.fgsEnabled) {
          val pending = store.countPendingForSessions(db, runSessionIds)
          val uploaded = store.countUploadedForSessions(db, runSessionIds)
          setForeground(
            buildForegroundInfo(
              title = "Subiendo imágenes",
              body = progressText(processedInRun, eligible.size, uploadedThisRun) +
                " · Sesión: $uploaded listas / $pending pendientes",
            ),
          )
        }
      }

      kickoffProcessIfReady(store, db, session, authCoordinator)

      when {
        authFailed -> Result.failure(workDataOf("error" to UploadContracts.CODE_AUTH_REQUIRED))
        reprepareNeeded && store.countPendingPrepared(db) == 0 ->
          Result.success(workDataOf("error" to UploadContracts.CODE_UPLOAD_REPREPARE_REQUIRED))
        needsRetry || store.countPendingPrepared(db) > 0 -> Result.retry()
        else -> Result.success()
      }
    } finally {
      try {
        db.close()
      } catch (_: Exception) {
      }
    }
  }

  private fun kickoffProcessIfReady(
    store: UploadSqliteStore,
    db: android.database.sqlite.SQLiteDatabase,
    session: NativeUploadAuthCoordinator.AuthSession,
    authCoordinator: NativeUploadAuthCoordinator,
  ) {
    val ready = store.listSessionsReadyForProcess(db)
    if (ready.isEmpty()) return
    val uploader = MultipartUploader(session.apiBaseUrl, session.apiKey)
    for (s in ready) {
      store.markProcessPending(db, s.sessionId)
      val idempotency = "mobile-process:${s.sessionId}"
      val mode = s.preparationProcessingMode
        ?.takeIf { it == "CODE_SCAN" || it == "INTERNAL_OCR" }
      var result = uploader.startProcess(
        s.inventoryId,
        s.aisleId,
        idempotency,
        mode,
        session.accessToken,
      )
      if (result.httpStatus == 401) {
        if (authCoordinator.refresh(session)) {
          result = uploader.startProcess(
            s.inventoryId,
            s.aisleId,
            idempotency,
            mode,
            session.accessToken,
          )
        } else {
          store.markProcessFailed(db, s.sessionId, UploadContracts.CODE_AUTH_REQUIRED, "Sesión vencida")
          continue
        }
      }
      val jobId = result.jobId
      if (!jobId.isNullOrBlank()) {
        store.markProcessStarted(db, s.sessionId, jobId)
        Log.i(TAG, "process started for session")
      } else {
        store.markProcessFailed(
          db,
          s.sessionId,
          result.errorCode ?: "PROCESS_FAILED",
          result.errorMessage ?: "process failed",
        )
      }
    }
  }

  private fun progressText(processed: Int, totalEligible: Int, uploadedOk: Int): String {
    return "Este run: $uploadedOk subidas · $processed/$totalEligible procesadas"
  }

  private fun buildForegroundInfo(title: String, body: String): ForegroundInfo {
    val notification = buildWorkerNotification(title, body)
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      ForegroundInfo(
        UploadContracts.NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
      )
    } else {
      ForegroundInfo(UploadContracts.NOTIFICATION_ID, notification)
    }
  }

  private fun buildWorkerNotification(title: String, body: String): Notification {
    val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      nm.createNotificationChannel(
        NotificationChannel(
          UploadContracts.NOTIFICATION_CHANNEL_ID,
          "Carga de imágenes",
          NotificationManager.IMPORTANCE_LOW,
        ).apply {
          description = "Progreso de carga en segundo plano"
          setShowBadge(false)
        },
      )
    }
    val launch = applicationContext.packageManager.getLaunchIntentForPackage(applicationContext.packageName)
    val contentPending = PendingIntent.getActivity(
      applicationContext,
      1,
      launch,
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    val pauseIntent = Intent(applicationContext, UploadPauseReceiver::class.java).apply {
      action = UploadPauseReceiver.ACTION_PAUSE_QUEUE
    }
    val pausePending = PendingIntent.getBroadcast(
      applicationContext,
      2,
      pauseIntent,
      PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    return NotificationCompat.Builder(applicationContext, UploadContracts.NOTIFICATION_CHANNEL_ID)
      .setContentTitle(title)
      .setContentText(body)
      .setSmallIcon(android.R.drawable.stat_sys_upload)
      .setOngoing(true)
      .setOnlyAlertOnce(true)
      .setContentIntent(contentPending)
      .addAction(0, "Pausar cola", pausePending)
      .setCategory(NotificationCompat.CATEGORY_PROGRESS)
      .build()
  }

  private fun retryAtIso(attempt: Int): String {
    val delay = min(60_000L, 1_000L * (1L shl min(attempt, 5)))
    return java.time.Instant.ofEpochMilli(System.currentTimeMillis() + delay).toString()
  }

  companion object {
    private const val TAG = "DinamicUploadWorker"
    private const val BATCH_LIMIT = 40
    private const val MAX_FILES_PER_REQUEST = 10

    fun networkTypeFor(allowMobileData: Boolean): NetworkType =
      if (allowMobileData) NetworkType.CONNECTED else NetworkType.UNMETERED

    /**
     * Schedule the single global upload queue.
     * @param replace when true (e.g. cellular preference changed), REPLACE unique work.
     */
    fun scheduleQueue(
      context: Context,
      expedited: Boolean = false,
      replace: Boolean = false,
    ) {
      val auth = AuthVault.read(context)
      if (!auth.available) {
        Log.w(TAG, "schedule skipped — ${UploadContracts.CODE_AUTH_VAULT_UNAVAILABLE}")
        return
      }
      if (!auth.workerEnabled) {
        Log.i(TAG, "schedule skipped — worker flag off")
        return
      }
      if (auth.queuePaused) {
        Log.i(TAG, "schedule skipped — queue paused")
        return
      }
      if (!auth.rebootResume) {
        // Still schedule while app is alive; BootReceiver cancels after reboot when off.
      }
      val constraints = Constraints.Builder()
        .setRequiredNetworkType(networkTypeFor(auth.allowMobileData))
        .build()
      val builder = OneTimeWorkRequestBuilder<DinamicUploadWorker>()
        .setConstraints(constraints)
        .addTag(UploadContracts.WORK_TAG)
        .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
      if (expedited) {
        builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
      }
      val policy = if (replace) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP
      WorkManager.getInstance(context).enqueueUniqueWork(
        UploadContracts.UNIQUE_QUEUE_NAME,
        policy,
        builder.build(),
      )
      Log.i(TAG, "scheduled unique work ${UploadContracts.UNIQUE_QUEUE_NAME} policy=$policy")
    }

    /** Pause queue: cancel work + OkHttp; persist paused. Does not clear local photos. */
    fun pauseQueue(context: Context) {
      AuthVault.setQueuePaused(context, true)
      ActiveUploadRegistry.cancelActive()
      WorkManager.getInstance(context).cancelUniqueWork(UploadContracts.UNIQUE_QUEUE_NAME)
      WorkManager.getInstance(context).cancelAllWorkByTag(UploadContracts.WORK_TAG)
      Log.i(TAG, "upload queue paused")
    }

    fun resumeQueue(context: Context) {
      AuthVault.setQueuePaused(context, false)
      scheduleQueue(context, expedited = true, replace = true)
    }

    fun cancelAll(context: Context) {
      ActiveUploadRegistry.cancelActive()
      WorkManager.getInstance(context).cancelAllWorkByTag(UploadContracts.WORK_TAG)
      WorkManager.getInstance(context).cancelUniqueWork(UploadContracts.UNIQUE_QUEUE_NAME)
    }

    fun statusSummary(context: Context): Map<String, Any?> {
      val infos = WorkManager.getInstance(context)
        .getWorkInfosForUniqueWork(UploadContracts.UNIQUE_QUEUE_NAME)
        .get()
      val state = infos.firstOrNull()?.state?.name ?: "NONE"
      val auth = AuthVault.read(context)
      val store = UploadSqliteStore(context)
      val open = store.open()
      val pending = when (open) {
        is UploadSqliteStore.OpenResult.Ok -> {
          val n = store.countPendingPrepared(open.db)
          open.db.close()
          n
        }
        is UploadSqliteStore.OpenResult.Failed -> -1
      }
      return mapOf(
        "uniqueWorkState" to state,
        "pendingPrepared" to pending,
        "running" to (infos.any { it.state == WorkInfo.State.RUNNING }),
        "queuePaused" to auth.queuePaused,
        "vaultAvailable" to auth.available,
      )
    }
  }
}
