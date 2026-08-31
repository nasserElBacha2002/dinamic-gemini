import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, FlatList, RefreshControl, Text, View } from 'react-native';

import { CreateAisleModal } from '../components/CreateAisleModal';
import type { CaptureSessionRow } from '../database/schema/captureSchema';
import {
  classifySessionsForAisle,
  workForAisle,
  type LocalAisleWork,
} from '../features/capture/localAisleWork';
import type { UploadSessionProgress } from '../features/upload/uploadQueue';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, Card, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';
import { checkOfflineRecognitionReadiness } from '../features/offlineRecognition';

function offlineReadinessMessage(status: string, missingKinds: readonly string[]): string {
  if (status === 'MISSING_SUPPLIER_PROFILE') {
    const kinds = missingKinds.length ? missingKinds.join('/') : 'ITEM/POSITION';
    return (
      `Falta el perfil de proveedor (${kinds}) para este pasillo.\n` +
      'Sincronizá la configuración offline con conexión antes de capturar. ' +
      'No se usa el perfil Dinamic como respaldo.'
    );
  }
  if (status === 'INCOMPATIBLE') {
    return 'La configuración offline no es compatible con esta versión de la app. Actualizá y sincronizá de nuevo.';
  }
  if (status === 'STALE') {
    return 'La configuración offline tiene más de 14 días. Conviene sincronizar con conexión.';
  }
  if (status === 'MISSING_BUNDLE') {
    return 'No hay configuración offline descargada. Con Dinamic podés continuar; para perfiles de proveedor sincronizá primero.';
  }
  return '';
}

export interface AislesScreenProps {
  services: AppServices;
  connectivity: 'online' | 'offline' | 'unknown';
  inventory: InventoryListItemDto;
  localSessions: CaptureSessionRow[];
  uploadProgress: readonly UploadSessionProgress[];
  exclusive: CaptureSessionRow | null;
  onSelectNew: (a: AisleDto) => void;
  onOpenWork: (work: LocalAisleWork) => void;
  onBack: () => void;
  onCancelCapture: () => void;
  onOpenPositionLabels?: () => void;
}

export function AislesScreen({
  services,
  connectivity,
  inventory,
  localSessions,
  uploadProgress,
  exclusive,
  onSelectNew,
  onOpenWork,
  onBack,
  onCancelCapture,
  onOpenPositionLabels,
}: AislesScreenProps) {
  const [items, setItems] = useState<AisleDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedAisleId, setExpandedAisleId] = useState<string | null>(null);
  const [offlineSyncAt, setOfflineSyncAt] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const load = useCallback(() => {
    setBusy(true);
    void services.aisles
      .list({ inventoryId: inventory.id, search })
      .then(async (res) => {
        setItems(res.items);
        if (connectivity === 'online') {
          const sync = await services.offlineRecognition.sync.syncInventory(inventory.id);
          if (sync.ok && sync.syncedAt) {
            setOfflineSyncAt(sync.syncedAt);
          }
        } else {
          const meta = await services.offlineRecognition.repo.getSyncMeta(inventory.id);
          setOfflineSyncAt(meta?.synced_at ?? null);
        }
      })
      .catch((e) => setError(messageOf(e)))
      .finally(() => setBusy(false));
  }, [inventory.id, search, services, connectivity]);
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    load();
  }, [load]);

  const openCreate = () => {
    if (connectivity === 'offline') {
      Alert.alert(
        'Sin conexión',
        'Necesitás conexión para crear un inventario o pasillo.\nLa captura existente puede continuar sin conexión.',
      );
      return;
    }
    setShowCreate(true);
  };

  const selectAisleWithOfflineGate = (aisle: AisleDto) => {
    if (connectivity !== 'offline') {
      onSelectNew(aisle);
      return;
    }
    void checkOfflineRecognitionReadiness({
      inventoryId: inventory.id,
      aisleId: aisle.id,
      repo: services.offlineRecognition.repo,
      resolver: services.offlineRecognition.resolver,
    }).then((ready) => {
      if (ready.status === 'MISSING_SUPPLIER_PROFILE' || ready.status === 'INCOMPATIBLE') {
        Alert.alert(
          'Configuración offline incompleta',
          offlineReadinessMessage(ready.status, ready.missingKinds),
        );
        return;
      }
      if (ready.status === 'STALE' || ready.status === 'MISSING_BUNDLE') {
        Alert.alert(
          'Aviso configuración offline',
          offlineReadinessMessage(ready.status, ready.missingKinds),
          [
            { text: 'Cancelar', style: 'cancel' },
            { text: 'Continuar', onPress: () => onSelectNew(aisle) },
          ],
        );
        return;
      }
      onSelectNew(aisle);
    });
  };

  return (
    <>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={load} />}
        ListHeaderComponent={
          <View>
            <SmallButton label="← Inventarios" onPress={onBack} />
            <Text style={styles.h2}>Pasillos · {inventory.name}</Text>
            {error ? <ErrorText text={error} /> : null}
            <Input placeholder="Buscar pasillo" value={search} onChangeText={setSearch} />
            <View style={styles.nav}>
              <Button label="Buscar" onPress={load} />
              <SmallButton label="+ Crear pasillo" onPress={openCreate} />
            </View>
            {connectivity === 'offline' ? (
              <Text style={styles.notif}>Modo sin conexión</Text>
            ) : null}
            <Text style={styles.row}>
              {offlineSyncAt
                ? `Configuración offline: ${offlineSyncAt.slice(0, 16).replace('T', ' ')}`
                : 'Configuración offline: sin sincronizar'}
            </Text>
            {connectivity === 'online' ? (
              <SmallButton
                label="Actualizar configuración offline"
                onPress={() => {
                  void services.offlineRecognition.sync
                    .syncInventory(inventory.id)
                    .then((r) => {
                      if (r.ok && r.syncedAt) setOfflineSyncAt(r.syncedAt);
                      else if (!r.ok) {
                        Alert.alert(
                          'Sync offline',
                          r.errorCode ?? 'No se pudo actualizar la configuración',
                        );
                      }
                    });
                }}
              />
            ) : null}
            {onOpenPositionLabels && inventory.client_id ? (
              <SmallButton
                label="Etiquetas de posicionamiento"
                onPress={onOpenPositionLabels}
              />
            ) : null}
          </View>
        }
        renderItem={({ item: aisle }) => {
          const work = workForAisle(localSessions, aisle.id, uploadProgress);
          const history = classifySessionsForAisle(localSessions, aisle.id, uploadProgress);
          const historyExtra = history.filter((h) => h.sessionId !== work?.sessionId);
          const exclusiveHere = Boolean(exclusive) && exclusive!.aisle_id === aisle.id;
          const expanded = expandedAisleId === aisle.id;
          return (
            <Card>
              <Text style={styles.cardTitle}>{aisle.code}</Text>
              <Text style={styles.row}>
                Estado: {aisle.status} · Activo: {aisle.is_active === false ? 'no' : 'sí'}
              </Text>
              <Text style={styles.row}>
                Fotos existentes: {aisle.assets_count} · Job: {aisle.latest_job?.status ?? '—'}
              </Text>
              {work && work.kind !== 'none' ? <Text style={styles.notif}>{work.label}</Text> : null}
              {history.length > 1 ? (
                <Text style={styles.row}>
                  {history.length} capturas locales en este pasillo
                </Text>
              ) : null}
              {work && work.kind !== 'none' && work.kind !== 'completed' ? (
                <Button
                  label={
                    work.kind === 'capture_paused'
                      ? 'Continuar captura'
                      : work.kind === 'capture_review'
                        ? 'Revisar fotos'
                        : work.kind === 'local_completed'
                          ? 'Abrir captura guardada'
                          : work.kind === 'uploading' || work.kind === 'ready_to_process'
                            ? 'Continuar cargas'
                            : work.kind === 'processing' || work.kind === 'failed_processing'
                              ? 'Ver procesamiento'
                              : 'Continuar'
                  }
                  onPress={() => onOpenWork(work)}
                />
              ) : null}
              {historyExtra.length > 0 ? (
                <SmallButton
                  label={expanded ? 'Ocultar historial' : 'Ver historial'}
                  onPress={() => setExpandedAisleId(expanded ? null : aisle.id)}
                />
              ) : null}
              {expanded
                ? historyExtra.map((h) => (
                    <View key={h.sessionId} style={styles.pendingBox}>
                      <Text style={styles.row}>
                        {h.label} · {h.shortId} · {h.updatedAt}
                      </Text>
                      <SmallButton label="Abrir" onPress={() => onOpenWork(h)} />
                    </View>
                  ))
                : null}
              {exclusiveHere ? <Button label="Cancelar captura" onPress={onCancelCapture} /> : null}
              <Button
                label={work && work.kind !== 'none' ? 'Comenzar nueva captura' : 'Seleccionar pasillo'}
                onPress={() => selectAisleWithOfflineGate(aisle)}
              />
            </Card>
          );
        }}
      />
      <CreateAisleModal
        visible={showCreate}
        services={services}
        inventory={inventory}
        onClose={() => setShowCreate(false)}
        onCreated={(created) => {
          setItems((prev) => [created, ...prev.filter((a) => a.id !== created.id)]);
          onSelectNew(created);
        }}
      />
    </>
  );
}
