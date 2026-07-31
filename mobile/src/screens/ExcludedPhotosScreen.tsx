/**
 * Fotos excluidas del pasillo actual — restore / requeue from Procesar pasillo hub.
 */

import { useCallback, useEffect, useState } from 'react';
import { Alert, FlatList, Image, Text, View } from 'react-native';

import type { CapturePhotoRow } from '../database/schema/captureSchema';
import {
  isExcludedPhoto,
  isSessionSealedForPhotoRestore,
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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [sealed, setSealed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    onError(null);
    try {
      const snap = await services.capture.loadSession(sessionId, false);
      setPhotos((snap.photos ?? []).filter(isExcludedPhoto));
      const sessions = await services.capture.listActivitySessions();
      const row = sessions.find((s) => s.id === sessionId);
      setSealed(row ? isSessionSealedForPhotoRestore(row) : false);
    } catch (e) {
      onError(messageOf(e));
    }
  }, [services, sessionId, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const restoreSelected = async () => {
    if (busy || selected.size === 0) return;
    if (sealed) {
      Alert.alert(
        'Sesión sellada',
        'No se puede modificar la secuencia de una sesión ya procesada. Creá una nueva captura para incluir fotos.',
      );
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      for (const id of selected) {
        const photo = photos.find((p) => p.id === id);
        if (!photo) continue;
        if (photo.status === 'excluded') {
          await services.capture.reincorporate(photo.asset_id);
        }
        if (photo.upload_status === 'excluded') {
          const r = await services.uploadQueue.requeueExcludedPhoto(photo.id);
          if (!r.ok) {
            setMessage(r.reason ?? 'No se pudo volver a incluir');
          }
        }
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
            {sealed ? (
              <ErrorText text="La sesión está sellada. No se pueden reincorporar fotos a esta secuencia." />
            ) : null}
            {message ? <Text style={styles.muted}>{message}</Text> : null}
            <View style={styles.nav}>
              <Button
                label={busy ? 'Incluyendo…' : 'Volver a incluir'}
                disabled={busy || selected.size === 0 || sealed}
                onPress={() => void restoreSelected()}
              />
            </View>
          </View>
        }
        ListEmptyComponent={
          <Text style={styles.muted}>No hay fotos excluidas en este pasillo.</Text>
        }
        renderItem={({ item }) => {
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
              <SmallButton
                label={active ? 'Seleccionada' : 'Seleccionar'}
                onPress={() => toggle(item.id)}
              />
            </View>
          );
        }}
      />
    </View>
  );
}
