import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, FlatList, RefreshControl, Text, View } from 'react-native';

import { CreateInventoryModal } from '../components/CreateInventoryModal';
import type { CaptureSessionRow } from '../database/schema/captureSchema';
import { workForAisle, type LocalAisleWork } from '../features/capture/localAisleWork';
import type { UploadSessionProgress } from '../features/upload/uploadQueue';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { InventoryListItemDto } from '../services/api/types';
import { Button, Card, ErrorText, Input, SmallButton, messageOf, styles } from '../ui';

export interface InventoriesScreenProps {
  services: AppServices;
  connectivity: 'online' | 'offline' | 'unknown';
  localSessions: CaptureSessionRow[];
  uploadProgress: readonly UploadSessionProgress[];
  onSelect: (i: InventoryListItemDto) => void;
  onOpenWork: (work: LocalAisleWork) => void;
}

export function InventoriesScreen({
  services,
  connectivity,
  localSessions,
  uploadProgress,
  onSelect,
  onOpenWork,
}: InventoriesScreenProps) {
  const [items, setItems] = useState<InventoryListItemDto[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const loadedRef = useRef(false);
  const load = useCallback(
    (nextPage = page) => {
      setBusy(true);
      setError(null);
      void services.inventories
        .list({ search, page: nextPage })
        .then((res) => {
          setItems(res.items);
          setPage(res.page);
          setTotalPages(Math.max(1, res.total_pages));
        })
        .catch((e) => setError(messageOf(e)))
        .finally(() => setBusy(false));
    },
    [page, search, services],
  );
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    load(1);
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

  const pendingByInventory = useMemo(() => {
    const map = new Map<string, LocalAisleWork[]>();
    for (const session of localSessions) {
      const upload = uploadProgress.find((u) => u.sessionId === session.id) ?? null;
      const work = workForAisle([session], session.aisle_id, upload ? [upload] : []);
      if (!work || work.kind === 'none' || work.kind === 'completed') continue;
      const list = map.get(session.inventory_id) ?? [];
      list.push(work);
      map.set(session.inventory_id, list);
    }
    return map;
  }, [localSessions, uploadProgress]);

  return (
    <>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={() => load(1)} />}
        ListHeaderComponent={
          <View>
            <Text style={styles.h2}>Inventarios</Text>
            {error ? <ErrorText text={error} /> : null}
            <Input placeholder="Buscar inventario" value={search} onChangeText={setSearch} />
            <View style={styles.nav}>
              <Button label="Buscar" onPress={() => load(1)} />
              <SmallButton label="+ Crear inventario" onPress={openCreate} />
            </View>
          </View>
        }
        ListEmptyComponent={!busy ? <Text style={styles.muted}>Sin inventarios.</Text> : null}
        ListFooterComponent={
          <View style={styles.nav}>
            <SmallButton label="Anterior" disabled={page <= 1} onPress={() => load(page - 1)} />
            <Text style={styles.row}>
              Página {page}/{totalPages}
            </Text>
            <SmallButton label="Siguiente" disabled={page >= totalPages} onPress={() => load(page + 1)} />
          </View>
        }
        renderItem={({ item }) => {
          const pending = pendingByInventory.get(item.id) ?? [];
          return (
            <Card>
              <Text style={styles.cardTitle}>{item.name}</Text>
              <Text style={styles.row}>
                Estado: {item.status} · Pasillos: {item.aisles_count}
              </Text>
              {pending.map((w) => (
                <View key={w.sessionId} style={styles.pendingBox}>
                  <Text style={styles.notif}>
                    {w.aisleName}: {w.label}
                  </Text>
                  <SmallButton label="Continuar" onPress={() => onOpenWork(w)} />
                </View>
              ))}
              <Button label="Seleccionar inventario" onPress={() => onSelect(item)} />
            </Card>
          );
        }}
      />
      <CreateInventoryModal
        visible={showCreate}
        services={services}
        onClose={() => setShowCreate(false)}
        onCreated={(created) => {
          setItems((prev) => [created, ...prev.filter((i) => i.id !== created.id)]);
          onSelect(created);
        }}
      />
    </>
  );
}
