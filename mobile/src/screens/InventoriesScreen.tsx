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

function formatSyncLabel(
  lastSyncedAt: string | null,
  connectivity: InventoriesScreenProps['connectivity'],
  syncing: boolean,
): string {
  if (syncing) {
    return 'Sincronizando...';
  }
  if (connectivity === 'offline') {
    return 'Offline';
  }
  if (!lastSyncedAt) {
    return 'Sin sincronizar';
  }
  return `Última sincronización: ${new Date(lastSyncedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function InventoriesScreen({
  services,
  connectivity,
  localSessions,
  uploadProgress,
  onSelect,
  onOpenWork,
}: InventoriesScreenProps) {
  const serverUploadEnabled = services.config.flags.mobileServerUpload !== false;
  const workOptions = { serverUploadEnabled };
  const [items, setItems] = useState<InventoryListItemDto[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const loadedRef = useRef(false);

  const applyLocalPage = useCallback(
    async (nextPage = page) => {
      const local = await services.inventories.listLocal({ search, page: nextPage });
      setItems(local.items);
      setPage(local.page);
      setTotalPages(Math.max(1, local.total_pages));
      const meta = await services.catalogRepo.getSyncMeta();
      setLastSyncedAt(meta?.last_successful_sync_at ?? meta?.last_synced_at ?? null);
      return local;
    },
    [page, search, services],
  );

  const load = useCallback(
    (nextPage = page, options?: { background?: boolean }) => {
      if (!options?.background) {
        setBusy(true);
      }
      setError(null);
      void applyLocalPage(nextPage)
        .then((local) => {
          if (connectivity === 'offline') {
            return local;
          }
          if (local.total_items === 0) {
            return services.inventories.list({ search, page: nextPage });
          }
          void services.catalog.requestSync('screen_refresh').then(async (result) => {
            if (result.syncedAt) {
              setLastSyncedAt(result.syncedAt);
            }
            if (result.status === 'FAILED' || result.status === 'PARTIAL') {
              setError('No se pudo actualizar. Se muestran datos guardados.');
            }
            await applyLocalPage(nextPage);
          });
          return local;
        })
        .then((res) => {
          if (res && 'items' in res && res !== undefined && connectivity !== 'offline' && res.total_items === 0) {
            setItems(res.items);
            setPage(res.page);
            setTotalPages(Math.max(1, res.total_pages));
          }
        })
        .catch((e) => setError(messageOf(e)))
        .finally(() => setBusy(false));
    },
    [applyLocalPage, connectivity, page, search, services],
  );

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    load(1);
  }, [load]);

  const manualSync = useCallback(() => {
    if (connectivity === 'offline') {
      Alert.alert('Sin conexión', 'Conectate para sincronizar el catálogo.');
      return;
    }
    setSyncing(true);
    void services.catalog
      .syncManual()
      .then(async (result) => {
        if (result.status === 'FAILED' || result.status === 'PARTIAL') {
          setError('No se pudo actualizar. Se muestran datos guardados.');
        } else {
          setError(null);
        }
        if (result.syncedAt) {
          setLastSyncedAt(result.syncedAt);
        }
        await applyLocalPage(page);
      })
      .finally(() => setSyncing(false));
  }, [applyLocalPage, connectivity, page, services.catalog]);

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
      const work = workForAisle([session], session.aisle_id, upload ? [upload] : [], workOptions);
      if (!work || work.kind === 'none' || work.kind === 'completed') continue;
      const list = map.get(session.inventory_id) ?? [];
      list.push(work);
      map.set(session.inventory_id, list);
    }
    return map;
  }, [localSessions, uploadProgress, workOptions]);

  const emptyMessage =
    connectivity === 'offline' && items.length === 0
      ? 'No hay datos disponibles para trabajar offline.\nConectate una vez para sincronizar el catálogo.'
      : 'Sin inventarios.';

  return (
    <>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={busy || syncing} onRefresh={() => load(1)} />}
        ListHeaderComponent={
          <View>
            <Text style={styles.h2}>Inventarios</Text>
            <Text style={styles.muted}>{formatSyncLabel(lastSyncedAt, connectivity, syncing)}</Text>
            {error ? <ErrorText text={error} /> : null}
            <Input placeholder="Buscar inventario" value={search} onChangeText={setSearch} />
            <View style={styles.nav}>
              <Button label="Buscar" onPress={() => load(1)} />
              <SmallButton label="Sincronizar" onPress={manualSync} />
              <SmallButton label="+ Crear inventario" onPress={openCreate} />
            </View>
          </View>
        }
        ListEmptyComponent={!busy ? <Text style={styles.muted}>{emptyMessage}</Text> : null}
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
