import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import type { ProcessingResultSummary } from '../features/processing/processingService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, styles } from '../ui';

export interface ResultsScreenProps {
  services: AppServices;
  sessionId: string;
  inventory: InventoryListItemDto | null;
  aisle: AisleDto | null;
  onBackToAisles: () => void;
  onAnotherAisle: () => void;
  onServerReprocess?: () => void;
  onError: (message: string | null) => void;
}

export function ResultsScreen({
  services,
  sessionId,
  inventory,
  aisle,
  onBackToAisles,
  onAnotherAisle,
  onServerReprocess,
  onError,
}: ResultsScreenProps) {
  const [busy, setBusy] = useState(true);
  const [summary, setSummary] = useState<ProcessingResultSummary | null>(null);

  const load = useCallback(() => {
    setBusy(true);
    void services.processing
      .getResultSummary(sessionId)
      .then((result) => {
        setSummary(result);
        if (result.loadState === 'error' && result.message) {
          onError(result.message);
        }
      })
      .catch((e) => {
        setSummary(null);
        onError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setBusy(false));
  }, [services, sessionId, onError]);

  useEffect(() => {
    load();
  }, [load]);

  if (busy && !summary) {
    return (
      <View>
        <ActivityIndicator color="#94d2bd" />
        <Text style={styles.muted}>Cargando resultado…</Text>
      </View>
    );
  }

  if (!summary) {
    return (
      <View>
        <ErrorText text="No se pudo cargar el resultado." />
        <Button label="Reintentar consulta" onPress={load} />
        <Button label="Volver a pasillos" onPress={onBackToAisles} />
      </View>
    );
  }

  const statusLabel =
    summary.loadState === 'complete'
      ? 'Resultado completo'
      : summary.loadState === 'partial'
        ? 'Resultado parcial'
        : summary.loadState === 'pending'
          ? 'Resultado todavía no disponible'
          : 'No se pudo consultar el resultado';

  return (
    <View>
      <Text style={styles.h2}>Resultado del procesamiento</Text>
      <Text style={styles.row}>{statusLabel}</Text>
      {summary.message ? <Text style={styles.muted}>{summary.message}</Text> : null}
      <Text style={styles.row}>Inventario: {summary.inventoryName}</Text>
      <Text style={styles.row}>Pasillo: {summary.aisleName}</Text>
      <Text style={styles.row}>Fotos procesadas: {summary.processedPhotos}</Text>
      <Text style={styles.row}>
        Posiciones detectadas:{' '}
        {summary.positions == null ? 'no disponible' : String(summary.positions)}
      </Text>
      <Text style={styles.row}>
        Pendientes de revisión:{' '}
        {summary.pendingReview == null ? 'no disponible' : String(summary.pendingReview)}
      </Text>
      {summary.finishedAt ? <Text style={styles.row}>Finalizado: {summary.finishedAt}</Text> : null}
      {summary.jobId ? <Text style={styles.muted}>Diagnóstico job: {summary.jobId}</Text> : null}
      {summary.loadState === 'error' || summary.loadState === 'pending' || summary.loadState === 'partial' ? (
        <Button label="Reintentar consulta" onPress={load} />
      ) : null}
      {onServerReprocess &&
      services.serverReprocess.isActionVisible() &&
      inventory &&
      aisle ? (
        <Button label="Reprocesar en el servidor" onPress={onServerReprocess} />
      ) : null}
      <Button label="Volver a pasillos" onPress={onBackToAisles} />
      <Button label="Capturar otro pasillo" onPress={onAnotherAisle} />
    </View>
  );
}
