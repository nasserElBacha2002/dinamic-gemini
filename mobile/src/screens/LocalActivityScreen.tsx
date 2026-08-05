import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Text, View } from 'react-native';

import {
  classifyLocalSession,
  type LocalAisleWork,
} from '../features/capture/localAisleWork';
import { canExportSession } from '../features/localCsv/canExportSession';
import {
  mapLocalCsvExportError,
  runLocalCsvExport,
  userMessageForLocalCsvExportError,
} from '../features/localCsv/runLocalCsvExport';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, Card, ErrorText, SmallButton, styles } from '../ui';

export interface LocalActivityScreenProps {
  services: AppServices;
  onOpenSession: (work: LocalAisleWork) => void;
  onBack: () => void;
  onError: (message: string | null) => void;
}

export function LocalActivityScreen({
  services,
  onOpenSession,
  onBack,
  onError,
}: LocalActivityScreenProps) {
  const [items, setItems] = useState<LocalAisleWork[]>([]);
  const [busy, setBusy] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [exportHints, setExportHints] = useState<Record<string, string>>({});

  const refresh = useCallback(() => {
    setBusy(true);
    void services.capture
      .listActivitySessions()
      .then((sessions) => {
        const uploadSnap = services.uploadQueue.getSnapshot();
        const mapped = sessions
          .map((s) =>
            classifyLocalSession(
              s,
              uploadSnap.sessions.find((u) => u.sessionId === s.id) ?? null,
            ),
          )
          .filter((w) => w.kind !== 'none');
        setItems(mapped);
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }, [onError, services]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const csvExport = services.config.flags.mobileCsvExport !== false;

  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.sessionId}
      ListHeaderComponent={
        <View>
          <SmallButton label="← Inventarios" onPress={onBack} />
          <Text style={styles.h2}>Actividad local</Text>
          <Text style={styles.row}>
            Consultá sesiones pendientes, resultados locales y progreso de subida sin depender de
            Internet.
          </Text>
          <Button label="Actualizar" disabled={busy} onPress={refresh} />
          {items.length === 0 && !busy ? (
            <ErrorText text="No hay sesiones locales abiertas." />
          ) : null}
        </View>
      }
      renderItem={({ item }) => {
        const exportableKind =
          item.kind === 'local_completed' || item.kind === 'capture_review';
        return (
          <Card>
            <Text style={styles.cardTitle}>
              {item.inventoryName} / {item.aisleName}
            </Text>
            <Text style={styles.row}>{item.label}</Text>
            <Text style={styles.row}>
              Actualizada: {item.updatedAt} · id {item.shortId}
              {item.frozenPhotoCount != null ? ` · fotos freeze: ${item.frozenPhotoCount}` : ''}
            </Text>
            <Text style={styles.row}>Pendientes de subir: {item.pendingUploads}</Text>
            {exportHints[item.sessionId] ? (
              <Text style={styles.notif}>{exportHints[item.sessionId]}</Text>
            ) : null}
            {exportingId === item.sessionId ? <ActivityIndicator /> : null}
            <Button label="Abrir" onPress={() => onOpenSession(item)} />
            {exportableKind && csvExport && services.localCsvExport ? (
              <Button
                label="Exportar ZIP (CSV + fotos)"
                disabled={exportingId !== null}
                onPress={() => {
                  setExportingId(item.sessionId);
                  void services.capture
                    .getSessionSnapshot(item.sessionId)
                    .then(async (snap) => {
                      const gate = canExportSession({
                        session: snap.session,
                        photos: snap.photos,
                        csvExportEnabled: csvExport,
                        exportInProgress: false,
                      });
                      if (!gate.ok) {
                        onError(gate.reason);
                        return;
                      }
                      const { exported } = await runLocalCsvExport(
                        services.localCsvExport!,
                        item.sessionId,
                      );
                      setExportHints((prev) => ({
                        ...prev,
                        [item.sessionId]: `Listo · ${exported.rowCount} filas · ${exported.photoCount} fotos${
                          exported.reused ? ' (reutilizado)' : ''
                        }`,
                      }));
                    })
                    .catch((e) => {
                      onError(userMessageForLocalCsvExportError(mapLocalCsvExportError(e)));
                    })
                    .finally(() => setExportingId(null));
                }}
              />
            ) : null}
          </Card>
        );
      }}
    />
  );
}
