/**
 * Fotos excluidas del pasillo actual — restore / requeue from Procesar pasillo hub.
 */

import { useCallback, useEffect, useState } from 'react';
import { Alert, FlatList, Image, Text, View } from 'react-native';

import type { CapturePhotoRow, CaptureSessionRow } from '../database/schema/captureSchema';
import {
  canRestoreExcludedPhoto,
  isExcludedPhoto,
} from '../features/processing/aisleProcessDialogHelpers';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, SmallButton, messageOf, styles } from '../ui';

export interface ExcludedPhotosScreenProps {
  services: AppServices;
  sessionId: string;
  inventoryName?: string;
  aisleName?: string;
  onBack: () => void;
  onError: (message: string | null) => void;
}

function exclusionLabel(photo: CapturePhotoRow): string {
  if (photo.status === 'excluded') return 'Excluida en captura';
  if (photo.upload_status === 'excluded') return 'Excluida de la cola';
  if (photo.upload_status === 'remote_delete_pending') return 'Eliminación remota pendiente';
  if (photo.upload_status === 'remote_deleted') return 'Eliminada del servidor';
  return 'Excluida';
}

export function ExcludedPhotosScreen({
  services,
  sessionId,
  inventoryName = '',
  aisleName = '',
  onBack,
  onError,
}: ExcludedPhotosScreenProps): JSX.Element {
  const [photos, setPhotos] = useState<CapturePhotoRow[]>([]);
  const [session, setSession] = useState<CaptureSessionRow | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    onError(null);
    try {
      const snap = await services.capture.loadSession(sessionId, false);
      setPhotos((snap.photos ?? []).filter(isExcludedPhoto));
      const sessions = await services.capture.listActivitySessions();
      setSession(sessions.find((s) => s.id === sessionId) ?? snap.session ?? null);
    } catch (e) {
      onError(messageOf(e));
    }
  }, [services, sessionId, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const restorableIds = new Set(
    session
      ? photos.filter((p) => canRestoreExcludedPhoto(session, p)).map((p) => p.id)
      : [],
  );
  const allBlocked = photos.length > 0 && restorableIds.size === 0;

  const toggle = (id: string) => {
    if (!restorableIds.has(id)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const restoreSelected = async () => {
    if (busy || selected.size === 0 || !session) return;
    const toRestore = [...selected].filter((id) => restorableIds.has(id));
    if (toRestore.length === 0) {
      Alert.alert(
        'No se puede reincorporar',
        'Estas fotos ya no se pueden volver a incluir en esta sesión (trabajo iniciado o eliminadas del servidor).',
      );
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      let requeued = false;
      for (const id of toRestore) {
        const photo = photos.find((p) => p.id === id);
        if (!photo) continue;
        if (photo.status === 'excluded') {
          await services.capture.reincorporate(photo.asset_id);
        }
        if (photo.upload_status === 'excluded') {
          const r = await services.uploadQueue.requeueExcludedPhoto(photo.id);
          if (!r.ok) {
            setMessage(r.reason ?? 'No se pudo volver a incluir');
          } else {
            requeued = true;
          }
        }
      }
      if (requeued) {
        await services.uploadQueue.enqueueSession(sessionId);
        await services.uploadQueue.resume();
      }
      setSelected(new Set());
      setMessage('Fotos reincorporadas. Revisá la galería o la cola de carga.');
      await reload();
    } catch (e) {
      onError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        data={photos}
        keyExtractor={(item) => item.id}
        ListHeaderComponent={
          <View>
            <SmallButton label="← Volver" onPress={onBack} />
            <Text style={styles.h2}>Fotos excluidas</Text>
            <Text style={styles.muted}>
              {inventoryName} / {aisleName}
            </Text>
            {allBlocked ? (
              <ErrorText text="No se pueden reincorporar estas fotos: la sesión ya tiene un trabajo de procesamiento o fueron eliminadas del servidor." />
            ) : (
              <Text style={styles.muted}>
                Las fotos excluidas de la cola (aún no subidas) se pueden volver a incluir y
                cargarán al servidor. Luego podés editar resultados en la app administrativa.
              </Text>
            )}
            {message ? <Text style={styles.muted}>{message}</Text> : null}
            <View style={styles.nav}>
              <Button
                label={busy ? 'Incluyendo…' : 'Volver a incluir'}
                disabled={busy || selected.size === 0}
                onPress={() => void restoreSelected()}
              />
            </View>
          </View>
        }
        ListEmptyComponent={
          <Text style={styles.muted}>No hay fotos excluidas en este pasillo.</Text>
        }
        renderItem={({ item }) => {
          const canRestore = session ? canRestoreExcludedPhoto(session, item) : false;
          const active = selected.has(item.id);
          return (
            <View style={[styles.photoCard, active ? styles.pickerItemActive : null]}>
              <Image source={{ uri: item.uri }} style={styles.thumb} />
              <Text style={styles.photoText} numberOfLines={1}>
                {item.display_name}
              </Text>
              <Text style={styles.muted}>{exclusionLabel(item)}</Text>
              {item.sequence_number != null ? (
                <Text style={styles.muted}>Secuencia: {item.sequence_number}</Text>
              ) : null}
              {!canRestore ? (
                <Text style={styles.muted}>No se puede reincorporar en esta sesión.</Text>
              ) : (
                <SmallButton
                  label={active ? 'Seleccionada' : 'Seleccionar'}
                  onPress={() => toggle(item.id)}
                />
              )}
            </View>
          );
        }}
      />
    </View>
  );
}
