/**
 * Combined local + server results for the current aisle session.
 */

import { useCallback, useEffect, useState } from 'react';
import { FlatList, Text, View } from 'react-native';

import type { AisleResultListItem } from '../features/processing/aisleProcessDialogHelpers';
import {
  buildLocalResultListItems,
  buildServerJobListItem,
  countPendingLocalResults,
} from '../features/processing/aisleProcessDialogHelpers';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, SmallButton, messageOf, styles } from '../ui';

export interface AisleResultsListScreenProps {
  services: AppServices;
  sessionId: string;
  inventoryName?: string;
  aisleName?: string;
  onBack: () => void;
  onViewServerResult: () => void;
  onUploadLocal: () => void;
  onError: (message: string | null) => void;
}

export function AisleResultsListScreen({
  services,
  sessionId,
  inventoryName = '',
  aisleName = '',
  onBack,
  onViewServerResult,
  onUploadLocal,
  onError,
}: AisleResultsListScreenProps): JSX.Element {
  const [items, setItems] = useState<AisleResultListItem[]>([]);
  const [busy, setBusy] = useState(true);
  const [syncBusy, setSyncBusy] = useState(false);
  const [pendingLocal, setPendingLocal] = useState(0);

  const reload = useCallback(async () => {
    setBusy(true);
    onError(null);
    try {
      const [localRows, view, snap] = await Promise.all([
        services.confirmedLocalResults.listForSession(sessionId),
        services.processing.getSessionProcessingView(sessionId),
        services.capture.loadSession(sessionId, false),
      ]);
      const localItems = buildLocalResultListItems(localRows);
      setPendingLocal(countPendingLocalResults(localRows));
      const serverItem = buildServerJobListItem({
        jobId: view?.jobId ?? snap.session?.backend_job_id ?? null,
        processingStatus: view?.state ?? snap.session?.processing_status ?? 'idle',
        updatedAt: view?.updatedAt ?? snap.session?.updated_at ?? new Date().toISOString(),
        photoCount: snap.photos?.length ?? null,
        errorMessage: view?.errorMessage ?? snap.session?.last_processing_error ?? null,
      });
      const merged = [...localItems];
      if (serverItem) merged.push(serverItem);
      setItems(merged);
    } catch (e) {
      onError(messageOf(e));
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, [services, sessionId, onError]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const syncLocal = async () => {
    if (syncBusy) return;
    setSyncBusy(true);
    try {
      const summary = await services.authoritativeLocalSync.syncPending();
      onError(null);
      await reload();
      if (summary.synced === 0 && summary.attempted === 0) {
        onError('No había resultados pendientes de subida.');
      }
    } catch (e) {
      onError(messageOf(e));
    } finally {
      setSyncBusy(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        ListHeaderComponent={
          <View>
            <SmallButton label="← Volver" onPress={onBack} />
            <Text style={styles.h2}>Resultados del pasillo</Text>
            <Text style={styles.muted}>
              {inventoryName} / {aisleName}
            </Text>
            {pendingLocal > 0 ? (
              <Text style={styles.muted}>{pendingLocal} resultado(s) local(es) pendiente(s)</Text>
            ) : null}
            <View style={styles.nav}>
              <SmallButton label="Actualizar" onPress={() => void reload()} />
              {pendingLocal > 0 ? (
                <Button
                  label={syncBusy ? 'Subiendo…' : 'Subir locales'}
                  disabled={syncBusy}
                  onPress={() => {
                    onUploadLocal();
                    void syncLocal();
                  }}
                />
              ) : null}
            </View>
            {busy ? <Text style={styles.muted}>Cargando…</Text> : null}
          </View>
        }
        ListEmptyComponent={
          !busy ? (
            <Text style={styles.muted}>Todavía no hay resultados para este pasillo.</Text>
          ) : null
        }
        renderItem={({ item }) => (
          <View style={[styles.pickerItem, { marginTop: 8 }]}>
            <Text style={styles.row}>{item.title}</Text>
            <Text style={styles.muted}>{item.subtitle}</Text>
            <Text style={styles.muted}>
              Origen: {item.origin === 'local' ? 'Local' : 'Servidor'} · Estado:{' '}
              {item.uiStatusLabel}
            </Text>
            {item.photoCount != null ? (
              <Text style={styles.muted}>Fotos: {item.photoCount}</Text>
            ) : null}
            {item.errorCode ? <ErrorText text={item.errorCode} /> : null}
            <View style={styles.nav}>
              {item.canUpload || item.canRetry ? (
                <SmallButton
                  label={item.canRetry ? 'Reintentar' : 'Subir al servidor'}
                  onPress={() => void syncLocal()}
                />
              ) : null}
              {item.origin === 'server' && item.canViewDetail ? (
                <SmallButton label="Ver detalle" onPress={onViewServerResult} />
              ) : null}
            </View>
          </View>
        )}
      />
    </View>
  );
}
