import { useCallback, useEffect, useState } from 'react';
import { FlatList, Image, Text, View } from 'react-native';

import { ProcessAisleConfirmModal } from '../components/ProcessAisleConfirmModal';
import { hasForeignUploadLease, UPLOAD_WORKER_OWNER_JS } from '../core/uploadLease';
import type { LocalDetectionDraftRow } from '../database/repositories/localDetectionDraftRepository';
import type { CapturePhotoRow } from '../database/schema/captureSchema';
import {
  formatLocalScanDetection,
  labelForLocalScanStatus,
  labelForPreliminarySyncStatus,
} from '../features/localCodeScan/localScanUi';
import type { AisleIdentificationMode } from '../features/processing/processingMode';
import {
  labelForIdentificationMode,
  preferenceFromSelection,
} from '../features/processing/processingMode';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, SmallButton, messageOf, styles } from '../ui';

function labelForUploadStatus(photo: CapturePhotoRow): string {
  if (photo.upload_cancel_requested === 1) {
    return 'Cancelando…';
  }
  if (photo.last_upload_error_code === 'UPLOAD_REPREPARE_REQUIRED') {
    return 'Requiere reapertura / repreparar';
  }
  if (
    hasForeignUploadLease({
      workerOwner: photo.upload_worker_owner,
      leaseExpiresAt: photo.upload_lease_expires_at,
      selfOwner: UPLOAD_WORKER_OWNER_JS,
    })
  ) {
    return 'Subiendo en segundo plano';
  }
  switch (photo.upload_status) {
    case 'not_queued':
      return 'Pendiente';
    case 'queued':
      return 'En cola';
    case 'preparing':
      return 'Preparando';
    case 'uploading':
      return 'Subiendo';
    case 'uploaded':
      return 'Completado';
    case 'retryable_error':
      return 'Reintentando';
    case 'permanent_error':
      return 'Error';
    case 'excluded':
      return 'Excluida';
    case 'remote_delete_pending':
      return 'Eliminación remota pendiente';
    case 'remote_deleted':
      return 'Eliminada';
    default:
      return photo.upload_status;
  }
}

function jsPauseHint(reason: string | null): string | null {
  switch (reason) {
    case 'offline':
      return 'Cola en pausa: sin conexión. Se reanuda al volver online.';
    case 'mobile_data':
      return 'Cola en pausa: datos móviles deshabilitados para cargas.';
    case 'auth':
    case 'logout':
      return 'Cola en pausa: sesión inválida. Volvé a iniciar sesión.';
    default:
      return reason ? `Cola en pausa (${reason}).` : null;
  }
}

function BackgroundUploadHint({
  services,
  onResume,
}: {
  services: AppServices;
  onResume: () => void;
}): JSX.Element | null {
  const [hint, setHint] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const apply = (jsPaused: string | null, nativePaused: boolean, nativeHint: string | null) => {
      if (cancelled) return;
      const jsHint = jsPauseHint(jsPaused);
      if (jsHint || nativePaused) {
        setPaused(true);
        setHint(jsHint ?? 'La cola nativa de carga está pausada. Tocá Reanudar.');
        return;
      }
      setPaused(false);
      setHint(nativeHint);
    };
    const tick = () => {
      const snap = services.uploadQueue.getSnapshot();
      if (!services.config.flags.backgroundUploadWorker) {
        apply(snap.pauseReason, false, null);
        return;
      }
      void services.backgroundUpload.getStatus().then((s) => {
        let nativeHint: string | null = null;
        if (s.mode === 'native' && (s.running || s.pendingPrepared > 0)) {
          nativeHint = 'Carga en segundo plano activa.';
        } else if (s.mode === 'native' && !s.vaultAvailable) {
          nativeHint = 'Credenciales nativas no disponibles — las cargas van con la app abierta.';
        }
        apply(snap.pauseReason, Boolean(s.mode === 'native' && s.queuePaused), nativeHint);
      });
    };
    tick();
    const unsub = services.uploadQueue.subscribe(() => tick());
    const id = setInterval(tick, 4000);
    return () => {
      cancelled = true;
      unsub();
      clearInterval(id);
    };
  }, [services]);
  if (!hint) return null;
  return (
    <View>
      <Text style={styles.muted}>{hint}</Text>
      {paused ? (
        <SmallButton
          label="Reanudar cola de carga"
          onPress={() => {
            void services.uploadQueue.resume().then(onResume);
          }}
        />
      ) : null}
    </View>
  );
}

export interface UploadsScreenProps {
  services: AppServices;
  sessionId: string;
  identificationModePreference: AisleIdentificationMode | null;
  onIdentificationModePreferenceChange: (next: AisleIdentificationMode | null) => void;
  onBack: () => void;
  onProcess: () => void;
  onError: (message: string | null) => void;
  /** Optional: open local confirm screen when authoritative review is enabled. */
  onLocalReview?: () => void;
  /** Phase 6: open authoritative finalize summary. */
  onAuthoritativeFinalize?: () => void;
}

export function UploadsScreen({
  services,
  sessionId,
  identificationModePreference,
  onIdentificationModePreferenceChange,
  onBack,
  onProcess,
  onError,
  onLocalReview,
  onAuthoritativeFinalize,
}: UploadsScreenProps) {
  const [progress, setProgress] = useState<Awaited<
    ReturnType<AppServices['uploadQueue']['getSessionProgress']>
  > | null>(null);
  const [photos, setPhotos] = useState<CapturePhotoRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [ready, setReady] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [localDraftByPhoto, setLocalDraftByPhoto] = useState<
    Record<string, LocalDetectionDraftRow>
  >({});
  const [localScanSummary, setLocalScanSummary] = useState<{
    scanned: number;
    resolved: number;
    unresolved: number;
  } | null>(null);
  const [authSyncPending, setAuthSyncPending] = useState(0);

  const refresh = useCallback(() => {
    void services.uploadQueue.getSessionProgress(sessionId).then(setProgress);
    void services.uploadQueue.refreshSessionReadiness(sessionId).then((r) => setReady(r === 'ready'));
    if (services.config.flags.mobileLocalCodeScan) {
      void services.localDetectionDrafts.listForSession(sessionId).then((rows) => {
        const byPhoto: Record<string, LocalDetectionDraftRow> = {};
        let scanned = 0;
        let resolved = 0;
        let unresolved = 0;
        for (const row of rows) {
          if (row.status === 'NOT_APPLICABLE') continue;
          scanned += 1;
          const prev = byPhoto[row.capture_photo_id];
          if (!prev || prev.status === 'NOT_APPLICABLE') {
            byPhoto[row.capture_photo_id] = row;
          }
          if (row.status === 'RESOLVED') resolved += 1;
          else if (
            row.status === 'UNRESOLVED' ||
            row.status === 'INVALID' ||
            row.status === 'AMBIGUOUS' ||
            row.status === 'FAILED' ||
            row.status === 'FAILED_RETRYABLE'
          ) {
            unresolved += 1;
          }
        }
        setLocalDraftByPhoto(byPhoto);
        setLocalScanSummary({ scanned, resolved, unresolved });
      });
    } else {
      setLocalDraftByPhoto({});
      setLocalScanSummary(null);
    }
    if (services.config.flags.mobileAuthoritativeLocalCodeScan) {
      void services.confirmedLocalResults.listForSession(sessionId).then((rows) => {
        setAuthSyncPending(
          rows.filter((r) => r.sync_status === 'PENDING' || r.sync_status === 'RETRY_SCHEDULED')
            .length,
        );
      });
    } else {
      setAuthSyncPending(0);
    }
  }, [services, sessionId]);
  useEffect(() => {
    // Entering Cargas: clear sticky native pause and drain JS queue for this session.
    void services.uploadQueue.resume().then(() => {
      void services.uploadQueue.enqueueSession(sessionId);
      refresh();
    });
  }, [services, sessionId, refresh]);

  useEffect(() => {
    refresh();
    const unsub = services.uploadQueue.subscribe(() => refresh());
    const t = setInterval(refresh, 2000);
    return () => {
      unsub();
      clearInterval(t);
    };
  }, [refresh, services]);
  useEffect(() => {
    const snap = services.capture.subscribe((s) => {
      if (s.session?.id === sessionId) setPhotos(s.photos);
    });
    void services.capture.loadSession(sessionId, false);
    return snap;
  }, [services, sessionId]);

  const uploadPhotos = photos.filter((p) => p.status === 'stable' || p.upload_status !== 'not_queued');

  const pendingUploads = uploadPhotos.filter(
    (p) =>
      p.upload_status === 'queued' ||
      p.upload_status === 'preparing' ||
      p.upload_status === 'uploading' ||
      p.upload_status === 'retryable_error' ||
      p.upload_status === 'not_queued',
  ).length;
  const uploadedCount = uploadPhotos.filter((p) => p.upload_status === 'uploaded').length;

  const openConfirm = () => {
    if (!ready || busy) return;
    setConfirmError(null);
    setConfirmVisible(true);
  };

  const retryAll = () => {
    if (retrying) return;
    setRetrying(true);
    onError(null);
    void services.uploadQueue
      .retrySession(sessionId)
      .then(() => refresh())
      .catch((e) => onError(messageOf(e)))
      .finally(() => setRetrying(false));
  };

  const confirmAndStart = (selection: import('../features/processing/processingMode').IdentificationModeSelection) => {
    if (busy) return;
    setBusy(true);
    setConfirmError(null);
    const modeAtConfirm = preferenceFromSelection(selection);
    onIdentificationModePreferenceChange(modeAtConfirm);
    void services.processing
      .startProcess(sessionId, { identificationMode: modeAtConfirm })
      .then(async (res) => {
        if (!res.ok) {
          setConfirmError(res.reason);
          onError(res.reason);
          return;
        }
        setConfirmVisible(false);
        if (res.jobId) await services.jobMonitor.watch(res.jobId);
        onProcess();
      })
      .catch((e) => {
        const msg = messageOf(e);
        setConfirmError(msg);
        onError(msg);
      })
      .finally(() => setBusy(false));
  };

  return (
    <>
      <FlatList
        data={uploadPhotos}
        keyExtractor={(item) => item.id}
        numColumns={2}
        columnWrapperStyle={styles.gridRow}
        initialNumToRender={8}
        maxToRenderPerBatch={8}
        windowSize={5}
        removeClippedSubviews
        ListHeaderComponent={
          <View>
            <SmallButton label="← Pasillos" onPress={onBack} />
            <Text style={styles.h2}>
              Cargas · {progress?.inventoryName ?? ''} / {progress?.aisleName ?? ''}
            </Text>
            <Text style={styles.row}>
              Cargadas: {progress?.uploaded ?? 0} · Pendientes: {progress?.pending ?? 0} · Subiendo:{' '}
              {progress?.uploading ?? 0} · Con error: {(progress?.retryable ?? 0) + (progress?.permanent ?? 0)}
            </Text>
            <BackgroundUploadHint services={services} onResume={refresh} />
            {uploadedCount > 0 && pendingUploads === 0 ? (
              <Text style={styles.muted}>
                Fotos ya en el servidor ({uploadedCount}). Siguiente paso: confirmar resultados
                locales (opcional) o «Procesar pasillo».
              </Text>
            ) : pendingUploads > 0 ? (
              <Text style={styles.muted}>
                Subiendo {pendingUploads} foto(s). Si no avanza, tocá «Reanudar cola» o
                «Reintentar todo».
              </Text>
            ) : (
              <Text style={styles.muted}>No hay fotos pendientes de carga en esta sesión.</Text>
            )}
            {authSyncPending > 0 ? (
              <Text style={styles.muted}>
                Sync de resultados locales confirmados: {authSyncPending} pendiente(s). No bloquea
                la carga de fotos; reintenta en segundo plano.
              </Text>
            ) : null}
            <Text style={styles.muted}>
              Tipo de trabajo: {labelForIdentificationMode(identificationModePreference)}
            </Text>
            {localScanSummary && localScanSummary.scanned > 0 ? (
              <Text style={styles.muted}>
                Escaneo local: {localScanSummary.scanned} · Detectadas:{' '}
                {localScanSummary.resolved} · Sin resolver: {localScanSummary.unresolved}
                {services.config.flags.mobileAuthoritativeLocalCodeScan
                  ? ' · Podés confirmar localmente o procesar en servidor'
                  : ' · El servidor confirma'}
              </Text>
            ) : null}
            <View style={styles.nav}>
              <SmallButton
                label={retrying ? 'Reintentando…' : 'Reintentar todo'}
                disabled={retrying}
                onPress={retryAll}
              />
              <SmallButton label="Actualizar" onPress={refresh} />
            </View>
            {onLocalReview &&
            (services.config.flags.mobileAuthoritativeLocalCodeScan ||
              services.config.flags.mobileLocalResultReview) ? (
              <SmallButton label="Confirmar resultados locales" onPress={onLocalReview} />
            ) : null}
            {onAuthoritativeFinalize &&
            services.config.flags.mobileAuthoritativeAisleFinalization ? (
              <SmallButton
                label="Finalizar pasillo (autoridad local)"
                onPress={onAuthoritativeFinalize}
              />
            ) : null}
            <Button
              label={busy ? 'Validando...' : 'Procesar pasillo'}
              disabled={!ready || busy}
              onPress={openConfirm}
            />
            {!ready ? (
              <Text style={styles.muted}>
                El procesamiento se habilita cuando no queden cargas pendientes ni errores recuperables.
              </Text>
            ) : null}
          </View>
        }
        ListEmptyComponent={<Text style={styles.muted}>Sin fotografías en cola.</Text>}
        renderItem={({ item: photo }) => {
          const draft = localDraftByPhoto[photo.id];
          const detection = formatLocalScanDetection(draft);
          return (
            <View style={styles.photoCard}>
              <Image source={{ uri: photo.uri }} style={styles.thumb} />
              <Text style={styles.photoText} numberOfLines={1}>
                {photo.display_name}
              </Text>
              <Text style={styles.photoText}>{labelForUploadStatus(photo)}</Text>
              {labelForLocalScanStatus(draft?.status) ? (
                <Text style={styles.muted} numberOfLines={2}>
                  {labelForLocalScanStatus(draft?.status)}
                </Text>
              ) : null}
              {detection ? (
                <Text style={styles.photoText} numberOfLines={2}>
                  {detection}
                </Text>
              ) : null}
              {services.config.flags.mobilePreliminaryDetectionSync &&
              labelForPreliminarySyncStatus(draft?.sync_status) ? (
                <Text style={styles.muted} numberOfLines={2}>
                  {labelForPreliminarySyncStatus(draft?.sync_status)}
                </Text>
              ) : null}
              {photo.upload_status === 'retryable_error' ||
              photo.upload_status === 'permanent_error' ? (
                <SmallButton
                  label="Reintentar"
                  onPress={() => void services.uploadQueue.retryPhoto(photo.id).then(refresh)}
                />
              ) : null}
              {photo.upload_status === 'uploaded' ? (
                <SmallButton
                  label="Excluir remoto"
                  onPress={() =>
                    void services.uploadQueue.excludeUploaded(sessionId, photo.id).then((r) => {
                      if (!r.ok) onError(r.reason);
                      refresh();
                    })
                  }
                />
              ) : (
                <SmallButton
                  label="Excluir cola"
                  onPress={() => void services.uploadQueue.cancelPhoto(photo.id).then(refresh)}
                />
              )}
            </View>
          );
        }}
      />
      <ProcessAisleConfirmModal
        visible={confirmVisible}
        inventoryName={progress?.inventoryName ?? ''}
        aisleName={progress?.aisleName ?? ''}
        uploadedCount={progress?.uploaded ?? 0}
        pendingCount={progress?.pending ?? 0}
        preference={identificationModePreference}
        busy={busy}
        error={confirmError}
        onClose={() => {
          if (busy) return;
          setConfirmVisible(false);
          setConfirmError(null);
        }}
        onConfirm={confirmAndStart}
      />
    </>
  );
}
