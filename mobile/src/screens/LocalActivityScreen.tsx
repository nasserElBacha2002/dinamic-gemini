import { useCallback, useEffect, useState } from 'react';
import { FlatList, Text, View } from 'react-native';

import {
  classifyLocalSession,
  type LocalAisleWork,
} from '../features/capture/localAisleWork';
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
      renderItem={({ item }) => (
        <Card>
          <Text style={styles.cardTitle}>
            {item.inventoryName} / {item.aisleName}
          </Text>
          <Text style={styles.row}>{item.label}</Text>
          <Text style={styles.row}>Pendientes de subir: {item.pendingUploads}</Text>
          <Button label="Abrir" onPress={() => onOpenSession(item)} />
        </Card>
      )}
    />
  );
}
