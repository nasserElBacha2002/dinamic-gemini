import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';

import type { ProcessingResultSummary } from '../features/processing/processingService';
import {
  formatPositionDetectionLine,
  PositionLabelDetectionsApi,
  type ImagePositionDetectionDto,
} from '../features/processing/positionLabelDetectionsApi';
import {
  formatPositionAssignmentLine,
  labelForAssignmentReason,
  PositionReconciliationApi,
  type ProductPositionAssignmentDto,
} from '../features/processing/positionReconciliationApi';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, styles } from '../ui';

type PositionFilter = 'all' | 'with_position' | 'without_position';

export interface ResultsScreenProps {
  services: AppServices;
  sessionId: string;
  inventory: InventoryListItemDto | null;
  aisle: AisleDto | null;
  onBackToAisles: () => void;
  onAnotherAisle: () => void;
  onServerReprocess?: () => void;
  onAisleRevision?: () => void;
  onAisleHistory?: () => void;
  onError: (message: string | null) => void;
}

function isAssigned(item: ProductPositionAssignmentDto): boolean {
  return Boolean(effectivePositionName(item));
}

function effectivePositionName(item: ProductPositionAssignmentDto): string | null {
  const effective = item.position?.name?.trim();
  if (effective) return effective;
  const automatic = item.position_name?.trim();
  return automatic || null;
}

export function ResultsScreen({
  services,
  sessionId,
  inventory,
  aisle,
  onBackToAisles,
  onAnotherAisle,
  onServerReprocess,
  onAisleRevision,
  onAisleHistory,
  onError,
}: ResultsScreenProps) {
  const [busy, setBusy] = useState(true);
  const [summary, setSummary] = useState<ProcessingResultSummary | null>(null);
  const [assignments, setAssignments] = useState<readonly ProductPositionAssignmentDto[]>([]);
  const [positionLines, setPositionLines] = useState<readonly string[]>([]);
  const [filter, setFilter] = useState<PositionFilter>('all');

  const load = useCallback(() => {
    setBusy(true);
    void services.processing
      .getResultSummary(sessionId)
      .then(async (result) => {
        setSummary(result);
        if (result.loadState === 'error' && result.message) {
          onError(result.message);
        }
        const invId = inventory?.id?.trim() || result.inventoryId?.trim();
        const jobId = result.jobId?.trim();
        if (!invId || !jobId) {
          setAssignments([]);
          setPositionLines([]);
          return;
        }
        try {
          const api = new PositionReconciliationApi(services.api);
          const response = await api.listAssignmentsForJob(invId, jobId);
          setAssignments(response.items ?? []);
        } catch {
          // Reconciliation is best-effort and may be disabled on the backend.
          setAssignments([]);
        }
        try {
          const api = new PositionLabelDetectionsApi(services.api);
          const response = await api.listForJob(invId, jobId);
          const lines = (response.items ?? [])
            .filter((item: ImagePositionDetectionDto) => item.status !== 'NO_LABEL')
            .map(formatPositionDetectionLine);
          setPositionLines(lines);
        } catch {
          // Detection query is best-effort; product summary remains primary.
          setPositionLines([]);
        }
      })
      .catch((e) => {
        setSummary(null);
        setAssignments([]);
        setPositionLines([]);
        onError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setBusy(false));
  }, [services, sessionId, inventory, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const filteredAssignments = useMemo(() => {
    if (filter === 'with_position') {
      return assignments.filter(isAssigned);
    }
    if (filter === 'without_position') {
      return assignments.filter((item) => !isAssigned(item));
    }
    return assignments;
  }, [assignments, filter]);

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
      {assignments.length > 0 ? (
        <View>
          <Text style={styles.h2}>Asignaciones de posición</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
            {(
              [
                ['all', 'Todos'],
                ['with_position', 'Con posición'],
                ['without_position', 'Sin posición'],
              ] as const
            ).map(([value, label]) => (
              <Pressable key={value} onPress={() => setFilter(value)}>
                <Text style={filter === value ? styles.h2 : styles.muted}>{label}</Text>
              </Pressable>
            ))}
          </View>
          {filteredAssignments.map((item) => (
            <View key={item.id} style={{ marginBottom: 8 }}>
              <Text style={styles.row}>
                Código: {item.result_id}
              </Text>
              <Text style={styles.row}>
                Posición:{' '}
                {isAssigned(item)
                  ? effectivePositionName(item)
                  : 'Sin asignar'}
              </Text>
              {item.position_assignment?.source === 'MANUAL' ? (
                <Text style={styles.muted}>Manual</Text>
              ) : null}
              {!isAssigned(item) ? (
                <Text style={styles.muted}>
                  Motivo: {labelForAssignmentReason(item.assignment_status)}
                </Text>
              ) : null}
              <Text style={styles.muted}>{formatPositionAssignmentLine(item)}</Text>
            </View>
          ))}
        </View>
      ) : null}
      {positionLines.length > 0 ? (
        <View>
          <Text style={styles.h2}>Etiquetas de posicionamiento</Text>
          {positionLines.map((line) => (
            <Text key={line} style={styles.row}>
              {line}
            </Text>
          ))}
        </View>
      ) : null}
      {summary.loadState === 'error' || summary.loadState === 'pending' || summary.loadState === 'partial' ? (
        <Button label="Reintentar consulta" onPress={load} />
      ) : null}
      {onServerReprocess &&
      services.serverReprocess.isActionVisible() &&
      inventory &&
      aisle ? (
        <Button label="Reprocesar en el servidor" onPress={onServerReprocess} />
      ) : null}
      {onAisleRevision &&
      services.aisleRevision.isActionVisible() &&
      inventory &&
      aisle ? (
        <Button label="Corregir pasillo" onPress={onAisleRevision} />
      ) : null}
      {onAisleHistory &&
      services.aisleRevision.isHistoryVisible() &&
      inventory &&
      aisle ? (
        <Button label="Historial del pasillo" onPress={onAisleHistory} />
      ) : null}
      <Button label="Volver a pasillos" onPress={onBackToAisles} />
      <Button label="Capturar otro pasillo" onPress={onAnotherAisle} />
    </View>
  );
}
