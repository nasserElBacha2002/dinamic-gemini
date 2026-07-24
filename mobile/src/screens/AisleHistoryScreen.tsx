import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import type { AisleRevisionHistoryEntryDto } from '../features/aisleRevision/aisleRevisionApi';
import { Button, ErrorText, styles } from '../ui';

export interface AisleHistoryScreenProps {
  services: AppServices;
  inventory: InventoryListItemDto;
  aisle: AisleDto;
  userId: string;
  onBack: () => void;
  onError: (message: string | null) => void;
}

function revisionTypeLabel(type: string): string {
  switch (type) {
    case 'MANUAL_CORRECTION':
      return 'Corrección manual';
    case 'SERVER_PROPOSAL_ADOPTION':
      return 'Adopción de propuesta';
    case 'ROLLBACK':
      return 'Reversión';
    case 'EXCLUSION_CHANGE':
      return 'Cambio de exclusión';
    case 'REOPEN_AND_EDIT':
      return 'Reabrir y editar';
    default:
      return type;
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'COMPLETED':
      return 'Completada';
    case 'OPEN':
    case 'DRAFT':
      return 'En curso';
    case 'CANCELED':
      return 'Cancelada';
    case 'FAILED':
      return 'Fallida';
    case 'CONFLICTED':
      return 'Conflicto';
    default:
      return status;
  }
}

export function AisleHistoryScreen({
  services,
  inventory,
  aisle,
  userId,
  onBack,
  onError,
}: AisleHistoryScreenProps) {
  const service = services.aisleRevision;
  const [busy, setBusy] = useState(true);
  const [entries, setEntries] = useState<readonly AisleRevisionHistoryEntryDto[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!service?.isHistoryVisible()) {
      setBusy(false);
      return;
    }
    setBusy(true);
    onError(null);
    void service
      .getHistory(inventory.id, aisle.id)
      .then(setEntries)
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }, [service, inventory.id, aisle.id, onError]);

  useEffect(() => {
    load();
  }, [load]);

  if (!service?.isHistoryVisible()) {
    return (
      <View>
        <ErrorText text="Historial de pasillo deshabilitado." />
        <Button label="Volver" onPress={onBack} />
      </View>
    );
  }

  const rollbackTo = (entry: AisleRevisionHistoryEntryDto) => {
    if (!service.isRollbackVisible()) {
      setMessage('La reversión está deshabilitada.');
      return;
    }
    setBusy(true);
    onError(null);
    void service
      .rollback({
        inventoryId: inventory.id,
        aisleId: aisle.id,
        targetFinalizationId: entry.base_finalization_id,
        reason: 'Reversión solicitada desde historial',
        requestedBy: userId,
      })
      .then(() => {
        setMessage('Reversión aplicada.');
        load();
      })
      .catch((e) => onError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <View>
      <Text style={styles.h2}>Historial del pasillo</Text>
      <Text style={styles.row}>Pasillo: {aisle.code ?? aisle.id}</Text>
      {busy && entries.length === 0 ? (
        <>
          <ActivityIndicator color="#94d2bd" />
          <Text style={styles.muted}>Cargando historial…</Text>
        </>
      ) : null}
      {!busy && entries.length === 0 ? (
        <Text style={styles.muted}>No hay correcciones registradas.</Text>
      ) : null}
      {entries.map((entry) => (
        <View key={entry.revision_id}>
          <Text style={styles.row}>
            {revisionTypeLabel(entry.revision_type)} · {statusLabel(entry.status)}
          </Text>
          <Text style={styles.muted}>
            {entry.changed_asset_count}/{entry.total_assets} imágenes ·{' '}
            {entry.requested_at?.slice(0, 19) ?? '—'}
          </Text>
          <Text style={styles.muted}>{entry.reason}</Text>
          {service.isRollbackVisible() && entry.new_finalization_id ? (
            <Button
              label="Volver a esta versión"
              onPress={() => rollbackTo(entry)}
            />
          ) : null}
        </View>
      ))}
      <Button label="Actualizar" onPress={load} />
      {message ? <Text style={styles.muted}>{message}</Text> : null}
      <Button label="Volver" onPress={onBack} />
    </View>
  );
}
