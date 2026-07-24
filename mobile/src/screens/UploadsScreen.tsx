import { useCallback, useEffect, useState } from 'react';
import { FlatList, Image, Text, View } from 'react-native';

import { ProcessAisleConfirmModal } from '../components/ProcessAisleConfirmModal';
import type { CapturePhotoRow } from '../database/schema/captureSchema';
import type { AisleIdentificationMode } from '../features/processing/processingMode';
import {
  labelForIdentificationMode,
  preferenceFromSelection,
} from '../features/processing/processingMode';
import { hasForeignUploadLease, UPLOAD_WORKER_OWNER_JS } from '../core/uploadLease';
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

function BackgroundUploadHint({ services }: { services: AppServices }): JSX.Element | null {
  const [hint, setHint] = useState<string | null>(null);
  useEffect(() => {
    if (!services.config.flags.backgroundUploadWorker) {
      setHint(null);
      return;
    }
    let cancelled = false;
    const tick = () => {
      void services.backgroundUpload.getStatus().then((s) => {
        if (cancelled) return;
        if (s.mode === 'native' && s.queuePaused) {
          setHint('Cola de carga en pausa. Abrí la app para reanudarla.');
        } else if (s.mode === 'native' && (s.running || s.pendingPrepared > 0)) {
          setHint(
            'La carga continuará en segundo plano cuando Android lo permita.',
          );
        } else if (s.mode === 'native' && !s.vaultAvailable) {
          setHint('Almacén de credenciales no disponible. Abrí la app con sesión activa.');
        } else if (s.mode === 'native') {
          setHint('Worker de carga en segundo plano disponible.');
        } else {
          setHint(null);
        }
      });
    };
    tick();
    const id = setInterval(tick, 4000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [services]);
  if (!hint) return null;
  return <Text style={styles.muted}>{hint}</Text>;
}

export interface UploadsScreenProps {
  services: AppServices;
  sessionId: string;
  identificationModePreference: AisleIdentificationMode | null;
  onIdentificationModePreferenceChange: (next: AisleIdentificationMode | null) => void;
  onBack: () => void;
  onProcess: () => void;
  onError: (message: string | null) => void;
}

export function UploadsScreen({
  services,
  sessionId,
  identificationModePreference,
  onIdentificationModePreferenceChange,
  onBack,
  onProcess,
  onError,
}: UploadsScreenProps) {
  const [progress, setProgress] = useState<Awaited<
    ReturnType<AppServices['uploadQueue']['getSessionProgress']>
  > | null>(null);
  const [photos, setPhotos] = useState<CapturePhotoRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void services.uploadQueue.getSessionProgress(sessionId).then(setProgress);
    void services.uploadQueue.refreshSessionReadiness(sessionId).then((r) => setReady(r === 'ready'));
  }, [services, sessionId]);
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

  const openConfirm = () => {
    if (!ready || busy) return;
    setConfirmError(null);
    setConfirmVisible(true);
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
            <BackgroundUploadHint services={services} />
            <Text style={styles.muted}>
              Tipo de trabajo: {labelForIdentificationMode(identificationModePreference)}
            </Text>
            <View style={styles.nav}>
              <SmallButton
                label="Reintentar todo"
                onPress={() => void services.uploadQueue.retrySession(sessionId).then(refresh)}
              />
              <SmallButton label="Actualizar" onPress={refresh} />
            </View>
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
        renderItem={({ item: photo }) => (
          <View style={styles.photoCard}>
            <Image source={{ uri: photo.uri }} style={styles.thumb} />
            <Text style={styles.photoText} numberOfLines={1}>
              {photo.display_name}
            </Text>
            <Text style={styles.photoText}>{labelForUploadStatus(photo)}</Text>
            {photo.upload_status === 'retryable_error' || photo.upload_status === 'permanent_error' ? (
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
        )}
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
