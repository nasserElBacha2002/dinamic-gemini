import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, FlatList, RefreshControl, Text, View } from 'react-native';

import { CreateAisleModal } from '../components/CreateAisleModal';
import type { CaptureSessionRow } from '../database/schema/captureSchema';
import { workForAisle, type LocalAisleWork } from '../features/capture/localAisleWork';
import type { UploadSessionProgress } from '../features/upload/uploadQueue';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, Card, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

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
}: AislesScreenProps) {
  const [items, setItems] = useState<AisleDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const loadedRef = useRef(false);
  const load = useCallback(() => {
    setBusy(true);
    void services.aisles
      .list({ inventoryId: inventory.id, search })
      .then((res) => setItems(res.items))
      .catch((e) => setError(messageOf(e)))
      .finally(() => setBusy(false));
  }, [inventory.id, search, services]);
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
          </View>
        }
        renderItem={({ item: aisle }) => {
          const work = workForAisle(localSessions, aisle.id, uploadProgress);
          const exclusiveHere = Boolean(exclusive) && exclusive!.aisle_id === aisle.id;
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
              {work && work.kind !== 'none' && work.kind !== 'completed' ? (
                <Button
                  label={
                    work.kind === 'capture_paused'
                      ? 'Continuar captura'
                      : work.kind === 'capture_review'
                        ? 'Revisar fotos'
                        : work.kind === 'uploading' || work.kind === 'ready_to_process'
                          ? 'Continuar cargas'
                          : work.kind === 'processing' || work.kind === 'failed_processing'
                            ? 'Ver procesamiento'
                            : 'Continuar'
                  }
                  onPress={() => onOpenWork(work)}
                />
              ) : null}
              {exclusiveHere ? <Button label="Cancelar captura" onPress={onCancelCapture} /> : null}
              <Button label="Seleccionar pasillo" onPress={() => onSelectNew(aisle)} />
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
