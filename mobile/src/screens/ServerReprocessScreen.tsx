import { useMemo, useState } from 'react';
import { Text, View } from 'react-native';

import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import type {
  ServerReprocessDetailDto,
  ServerReprocessProcessingMode,
  ServerReprocessScopeType,
} from '../features/serverReprocess/serverReprocessApi';
import { Button, ErrorText, styles } from '../ui';

export interface ServerReprocessScreenProps {
  services: AppServices;
  inventory: InventoryListItemDto;
  aisle: AisleDto;
  initialRunId?: string | null;
  onBack: () => void;
  onError: (message: string | null) => void;
}

const SCOPES: { value: ServerReprocessScopeType; label: string }[] = [
  { value: 'FULL_AISLE', label: 'Todo el pasillo' },
  { value: 'FAILED_ONLY', label: 'Solo imágenes con errores' },
  { value: 'SELECTED_ASSETS', label: 'Seleccionar imágenes (próximamente: full aisle)' },
];

const MODES: { value: ServerReprocessProcessingMode; label: string }[] = [
  { value: 'CODE_SCAN', label: 'CODE_SCAN' },
  { value: 'INTERNAL_OCR', label: 'OCR' },
  { value: 'AUTO_PIPELINE', label: 'Pipeline automático' },
];

export function ServerReprocessScreen({
  services,
  inventory,
  aisle,
  initialRunId,
  onBack,
  onError,
}: ServerReprocessScreenProps) {
  const service = services.serverReprocess;
  const [scope, setScope] = useState<ServerReprocessScopeType>('FULL_AISLE');
  const [mode, setMode] = useState<ServerReprocessProcessingMode>('CODE_SCAN');
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState<string | null>(initialRunId ?? null);
  const [detail, setDetail] = useState<ServerReprocessDetailDto | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const warning = useMemo(
    () => 'Los resultados actuales no se reemplazarán automáticamente.',
    [],
  );

  if (!service?.isActionVisible()) {
    return (
      <View>
        <ErrorText text="Reprocesamiento en servidor deshabilitado." />
        <Button label="Volver" onPress={onBack} />
      </View>
    );
  }

  const request = () => {
    setBusy(true);
    setMessage(null);
    onError(null);
    void service
      .requestReprocess({
        inventoryId: inventory.id,
        aisleId: aisle.id,
        scopeType: scope === 'SELECTED_ASSETS' ? 'FULL_AISLE' : scope,
        processingMode: mode,
      })
      .then(async (result) => {
        if ('pending' in result) {
          setMessage('Solicitud guardada offline. Se enviará al recuperar conexión.');
          return;
        }
        setRunId(result.id);
        setMessage(
          result.initial_server_processing
            ? 'Corrida servidor inicial creada (sin comparación previa).'
            : 'Corrida de reproceso creada. Esperá propuestas del servidor.',
        );
        if (service.isReviewVisible()) {
          const d = await service.getRun(inventory.id, aisle.id, result.id);
          setDetail(d);
        }
      })
      .catch((e) => {
        const text = e instanceof Error ? e.message : String(e);
        setMessage(text);
        onError(text);
      })
      .finally(() => setBusy(false));
  };

  const refresh = () => {
    if (!runId) return;
    setBusy(true);
    void service
      .getRun(inventory.id, aisle.id, runId)
      .then(setDetail)
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  const adoptChanged = () => {
    if (!detail || !runId || !service.isReviewVisible()) return;
    const items = detail.items
      .filter((i) => i.difference_type !== 'SAME_RESULT')
      .filter((i) => !i.difference_type.startsWith('NOT_COMPARABLE'))
      .map((i) => ({ proposal_id: i.id, action: 'ADOPT' as const }));
    const keep = detail.items
      .filter((i) => i.difference_type === 'SAME_RESULT')
      .map((i) => ({ proposal_id: i.id, action: 'KEEP_CURRENT' as const }));
    if (items.length === 0) {
      setMessage('No hay cambios para adoptar.');
      return;
    }
    setBusy(true);
    void service
      .adopt(inventory.id, aisle.id, runId, [...items, ...keep])
      .then((res) => {
        setMessage(`Cambios aplicados. Estado: ${res.review_status}`);
        refresh();
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <View>
      <Text style={styles.h2}>Reprocesar en el servidor</Text>
      <Text style={styles.muted}>{warning}</Text>
      <Text style={styles.row}>Pasillo: {aisle.code ?? aisle.id}</Text>

      {!runId ? (
        <>
          <Text style={styles.row}>¿Qué querés reprocesar?</Text>
          {SCOPES.map((s) => (
            <Button
              key={s.value}
              label={`${scope === s.value ? '●' : '○'} ${s.label}`}
              onPress={() => setScope(s.value)}
            />
          ))}
          <Text style={styles.row}>¿Cómo querés procesarlas?</Text>
          {MODES.map((m) => (
            <Button
              key={m.value}
              label={`${mode === m.value ? '●' : '○'} ${m.label}`}
              onPress={() => setMode(m.value)}
            />
          ))}
          <Button label={busy ? 'Solicitando…' : 'Solicitar reproceso'} onPress={request} />
        </>
      ) : (
        <>
          <Text style={styles.row}>Corrida: {runId}</Text>
          <Button label="Actualizar propuesta" onPress={refresh} />
          {detail ? (
            <>
              <Text style={styles.row}>
                Resumen: {detail.summary.same} iguales · {detail.summary.changed} cambiaron ·{' '}
                {detail.summary.newly_resolved} nuevos
              </Text>
              {detail.items.slice(0, 8).map((item) => (
                <Text key={item.id} style={styles.muted}>
                  {item.asset_id}: {item.difference_type} → {item.internal_code ?? '—'}
                </Text>
              ))}
              {service.isReviewVisible() ? (
                <Button label="Aplicar solo cambios" onPress={adoptChanged} />
              ) : null}
            </>
          ) : (
            <Text style={styles.muted}>
              Cuando el servidor termine, actualizá para revisar la propuesta.
            </Text>
          )}
        </>
      )}

      {message ? <Text style={styles.muted}>{message}</Text> : null}
      <Button label="Volver" onPress={onBack} />
    </View>
  );
}
