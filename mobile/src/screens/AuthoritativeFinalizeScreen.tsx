import { useCallback, useEffect, useState } from 'react';
import { Alert, Text, View } from 'react-native';

import type { AuthoritativeAisleReadiness } from '../features/authoritativeAisleFinalization/authoritativeAisleReadiness';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, SmallButton, messageOf, styles } from '../ui';

export interface AuthoritativeFinalizeScreenProps {
  services: AppServices;
  sessionId: string;
  inventoryId: string;
  aisleId: string;
  inventoryName: string;
  aisleName: string;
  onBack: () => void;
  onCompleted: () => void;
  onError: (message: string | null) => void;
}

export function AuthoritativeFinalizeScreen({
  services,
  sessionId,
  inventoryId,
  aisleId,
  inventoryName,
  aisleName,
  onBack,
  onCompleted,
  onError,
}: AuthoritativeFinalizeScreenProps): JSX.Element {
  const [local, setLocal] = useState<AuthoritativeAisleReadiness | null>(null);
  const [server, setServer] = useState<AuthoritativeAisleReadiness | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    void services.authoritativeAisleFinalization.evaluateLocal(sessionId).then(setLocal);
    void services.authoritativeAisleFinalization
      .refreshServerReadiness(inventoryId, aisleId)
      .then(setServer)
      .catch((e) => onError(messageOf(e)));
  }, [services, sessionId, inventoryId, aisleId, onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const ready = server?.status === 'READY';
  const display = server ?? local;

  const confirmFinalize = () => {
    if (!ready || busy) return;
    Alert.alert(
      'Finalizar pasillo',
      'Este pasillo se finalizará con los resultados confirmados en la aplicación.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Volver a revisar',
          onPress: onBack,
        },
        {
          text: 'Finalizar pasillo',
          style: 'destructive',
          onPress: () => {
            setBusy(true);
            onError(null);
            void services.authoritativeAisleFinalization
              .finalize({ sessionId, inventoryId, aisleId })
              .then((res) => {
                if (!res.ok) {
                  onError(res.reason);
                  return;
                }
                onCompleted();
              })
              .catch((e) => onError(messageOf(e)))
              .finally(() => setBusy(false));
          },
        },
      ],
    );
  };

  return (
    <View>
      <SmallButton label="← Cargas" onPress={onBack} />
      <Text style={styles.h2}>
        Finalizar · {inventoryName} / {aisleName}
      </Text>
      <Text style={styles.muted}>
        Este pasillo se finalizará con los resultados confirmados en la aplicación.
      </Text>
      {display ? (
        <View>
          <Text style={styles.row}>Estado: {display.status}</Text>
          <Text style={styles.muted}>
            Totales: {display.totalImages} · Aplicadas: {display.appliedImages} · Excluidas:{' '}
            {display.excludedImages}
          </Text>
          <Text style={styles.muted}>
            Pendientes: {display.pendingImages} · Conflictos: {display.conflictedImages} ·
            Errores: {display.failedImages}
          </Text>
          <Text style={styles.muted}>
            Códigos únicos: {display.uniqueCodes} · Cantidad total: {display.totalQuantity}
          </Text>
          {display.reasons.length > 0 ? (
            <Text style={styles.muted}>Razones: {display.reasons.join(', ')}</Text>
          ) : null}
        </View>
      ) : (
        <Text style={styles.muted}>Evaluando readiness…</Text>
      )}
      <View style={styles.nav}>
        <SmallButton label="Actualizar" onPress={refresh} />
        <SmallButton label="Volver a revisar" onPress={onBack} />
      </View>
      <Button
        label={busy ? 'Finalizando…' : 'Finalizar pasillo'}
        disabled={!ready || busy}
        onPress={confirmFinalize}
      />
      {!ready ? (
        <Text style={styles.muted}>
          El botón se habilita cuando el servidor confirma READY (todas aplicadas o excluidas).
        </Text>
      ) : null}
    </View>
  );
}
