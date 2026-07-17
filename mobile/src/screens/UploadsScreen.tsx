import { useCallback, useEffect, useState } from 'react';
import { FlatList, Image, Text, View } from 'react-native';

import type { CapturePhotoRow } from '../database/schema/captureSchema';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, SmallButton, messageOf, styles } from '../ui';

export interface UploadsScreenProps {
  services: AppServices;
  sessionId: string;
  onBack: () => void;
  onProcess: () => void;
  onError: (message: string | null) => void;
}

export function UploadsScreen({ services, sessionId, onBack, onProcess, onError }: UploadsScreenProps) {
  const [progress, setProgress] = useState<Awaited<
    ReturnType<AppServices['uploadQueue']['getSessionProgress']>
  > | null>(null);
  const [photos, setPhotos] = useState<CapturePhotoRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
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

  return (
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
            onPress={() => {
              setBusy(true);
              void services.processing
                .startProcess(sessionId)
                .then(async (res) => {
                  if (!res.ok) {
                    onError(res.reason);
                    return;
                  }
                  if (res.jobId) await services.jobMonitor.watch(res.jobId);
                  onProcess();
                })
                .catch((e) => onError(messageOf(e)))
                .finally(() => setBusy(false));
            }}
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
          <Text style={styles.photoText}>upload: {photo.upload_status}</Text>
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
  );
}
