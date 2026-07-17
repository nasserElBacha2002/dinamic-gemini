import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  RefreshControl,
  Share,
  StyleSheet,
  TextInput,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import type { AppServices } from './src/runtime/bootstrap/createAppServices';
import { createAppServices } from './src/runtime/bootstrap/createAppServices';
import type { CaptureContext, CaptureSnapshot } from './src/features/capture/captureService';
import type { AuthSession } from './src/features/auth/authService';
import type { AisleDto, InventoryListItemDto } from './src/services/api/types';
import { getPhotoPermission, requestPhotoPermission } from './src/native/mediaStore';
import type { CapturePhotoRow, CaptureSessionRow } from './src/database/schema/captureSchema';
import type { HealthCheckResult } from './src/features/support/healthChecks';
import { userMessageForCode } from './src/core/errorCatalog';
import { isCaptureExclusiveSession } from './src/core/captureState';
import {
  findExclusiveCapture,
  workForAisle,
  type LocalAisleWork,
} from './src/features/capture/localAisleWork';
import type { UploadSessionProgress } from './src/features/upload/uploadQueue';

type Screen =
  | 'login'
  | 'inventories'
  | 'aisles'
  | 'capture'
  | 'review'
  | 'uploads'
  | 'processing'
  | 'diagnostic';

export default function App(): JSX.Element {
  const [services, setServices] = useState<AppServices | null>(null);
  const [screen, setScreen] = useState<Screen>('login');
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedInventory, setSelectedInventory] = useState<InventoryListItemDto | null>(null);
  const [selectedAisle, setSelectedAisle] = useState<AisleDto | null>(null);
  const [capture, setCapture] = useState<CaptureSnapshot | null>(null);
  const [workSessionId, setWorkSessionId] = useState<string | null>(null);
  const [connectivity, setConnectivity] = useState<'online' | 'offline' | 'unknown'>('unknown');
  const [localSessions, setLocalSessions] = useState<CaptureSessionRow[]>([]);
  const [uploadProgress, setUploadProgress] = useState<readonly UploadSessionProgress[]>([]);

  useEffect(() => {
    let mounted = true;
    let unsubscribeCapture: (() => void) | undefined;
    let unsubscribeConnectivity: (() => void) | undefined;
    let unsubscribeUpload: (() => void) | undefined;
    let createdServices: AppServices | undefined;
    void createAppServices(() => {
      setAuth(null);
      setScreen('login');
      void createdServices?.uploadQueue.pause('auth');
    })
      .then(async (created) => {
        if (!mounted) return;
        createdServices = created;
        setServices(created);
        setConfigError(created.configError);
        unsubscribeConnectivity = created.connectivity.subscribe((state) => {
          if (mounted) setConnectivity(state);
        });
        unsubscribeUpload = created.uploadQueue.subscribe((snap) => {
          if (mounted) setUploadProgress(snap.sessions);
        });
        const restored = created.configError ? null : await created.auth.restore();
        if (!mounted) return;
        setAuth(restored);
        const open = await created.capture.restoreLatestOpen();
        const activity = await created.capture.listActivitySessions();
        if (mounted) setLocalSessions(activity);
        unsubscribeCapture = created.capture.subscribe((snapshot) => {
          if (mounted) setCapture(snapshot);
        });
        if (restored) {
          routeAfterRestore(open, setScreen, setWorkSessionId, setSelectedInventory, setSelectedAisle);
        }
        setLoading(false);
      })
      .catch((e) => {
        setError(messageOf(e));
        setLoading(false);
      });
    return () => {
      mounted = false;
      unsubscribeCapture?.();
      unsubscribeConnectivity?.();
      unsubscribeUpload?.();
      void createdServices?.dispose();
    };
  }, []);

  const refreshLocalWork = useCallback(() => {
    if (!services) return;
    void services.capture.listActivitySessions().then(setLocalSessions);
  }, [services]);

  useEffect(() => {
    if (!services || !auth) return;
    refreshLocalWork();
    const t = setInterval(refreshLocalWork, 4000);
    return () => clearInterval(t);
  }, [services, auth, refreshLocalWork, screen]);

  if (loading || !services) {
    return (
      <Shell title="Dinamic Captura">
        <ActivityIndicator color="#94d2bd" />
      </Shell>
    );
  }

  if (configError) {
    return (
      <Shell title="Configuración">
        <ErrorText text={configError} />
      </Shell>
    );
  }

  if (!auth || screen === 'login') {
    return (
      <LoginScreen
        services={services}
        onLoggedIn={(session) => {
          setAuth(session);
          setScreen('inventories');
        }}
      />
    );
  }

  const openAisleWork = (work: LocalAisleWork, inventory: InventoryListItemDto | null) => {
    setWorkSessionId(work.sessionId);
    if (inventory) setSelectedInventory(inventory);
    setSelectedAisle({
      id: work.aisleId,
      inventory_id: work.inventoryId,
      code: work.aisleName,
      status: 'created',
      created_at: '',
      updated_at: '',
      is_active: true,
      assets_count: 0,
      positions_count: 0,
      pending_review_positions_count: 0,
    });
    if (work.kind === 'capture_active' || work.kind === 'capture_paused') {
      void services.capture.loadSession(work.sessionId, work.kind === 'capture_active');
      setScreen('capture');
    } else if (work.kind === 'capture_review') {
      void services.capture.loadSession(work.sessionId, false);
      setScreen('review');
    } else if (work.kind === 'uploading' || work.kind === 'ready_to_process') {
      setScreen('uploads');
    } else {
      setScreen('processing');
    }
  };

  return (
    <Shell
      title="Dinamic Captura"
      footer={
        <View style={styles.nav}>
          <SmallButton label="Inventarios" onPress={() => setScreen('inventories')} />
          <SmallButton label="Diagnóstico" onPress={() => setScreen('diagnostic')} />
          <SmallButton
            label="Salir"
            onPress={() =>
              void services.auth.logout().finally(() => {
                setAuth(null);
                setScreen('login');
              })
            }
          />
        </View>
      }
    >
      {error ? <ErrorText text={error} /> : null}
      {connectivity === 'offline' ? <ErrorText text={userMessageForCode('NETWORK_OFFLINE')} /> : null}
      {screen === 'inventories' ? (
        <InventoriesScreen
          services={services}
          localSessions={localSessions}
          uploadProgress={uploadProgress}
          onSelect={(inventory) => {
            setSelectedInventory(inventory);
            setScreen('aisles');
          }}
          onOpenWork={(work) => openAisleWork(work, null)}
        />
      ) : null}
      {screen === 'aisles' && selectedInventory ? (
        <AislesScreen
          services={services}
          inventory={selectedInventory}
          localSessions={localSessions}
          uploadProgress={uploadProgress}
          exclusive={findExclusiveCapture(localSessions)}
          onBack={() => setScreen('inventories')}
          onSelectNew={(aisle) => {
            setSelectedAisle(aisle);
            setScreen('capture');
          }}
          onOpenWork={(work) => openAisleWork(work, selectedInventory)}
          onCancelCapture={() =>
            Alert.alert('Cancelar captura', 'No se borran fotos del teléfono.', [
              { text: 'No' },
              {
                text: 'Cancelar captura',
                style: 'destructive',
                onPress: () => void services.capture.cancel().then(refreshLocalWork),
              },
            ])
          }
        />
      ) : null}
      {screen === 'capture' && (capture?.context || (selectedInventory && selectedAisle)) ? (
        <CaptureScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          snapshot={capture}
          onReview={() => setScreen('review')}
          onBackToAisles={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onError={setError}
        />
      ) : null}
      {screen === 'review' ? (
        <ReviewScreen
          services={services}
          snapshot={capture}
          onBack={() => setScreen('capture')}
          onDone={(sessionId) => {
            setWorkSessionId(sessionId);
            void services.uploadQueue.enqueueSession(sessionId);
            setScreen('uploads');
          }}
          onError={setError}
        />
      ) : null}
      {screen === 'uploads' && workSessionId ? (
        <UploadsScreen
          services={services}
          sessionId={workSessionId}
          onBack={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onProcess={() => setScreen('processing')}
          onError={setError}
        />
      ) : null}
      {screen === 'processing' && workSessionId ? (
        <ProcessingScreen
          services={services}
          sessionId={workSessionId}
          onBack={() => setScreen(selectedInventory ? 'aisles' : 'inventories')}
          onAnotherAisle={() => setScreen('inventories')}
          onError={setError}
        />
      ) : null}
      {screen === 'diagnostic' ? (
        <DiagnosticScreen services={services} onBack={() => setScreen('inventories')} />
      ) : null}
    </Shell>
  );
}

function routeAfterRestore(
  open: CaptureSessionRow | null,
  setScreen: (s: Screen) => void,
  setWorkSessionId: (id: string | null) => void,
  setSelectedInventory: (i: InventoryListItemDto | null) => void,
  setSelectedAisle: (a: AisleDto | null) => void,
): void {
  if (!open) {
    setScreen('inventories');
    return;
  }
  setWorkSessionId(open.id);
  setSelectedInventory({
    id: open.inventory_id,
    name: open.inventory_name,
    status: 'draft',
    client_id: null,
    created_at: null,
    updated_at: null,
    aisles_count: 0,
    pending_review_count: 0,
    last_activity_at: null,
    processing_mode: 'production',
  });
  setSelectedAisle({
    id: open.aisle_id,
    inventory_id: open.inventory_id,
    code: open.aisle_name,
    status: 'created',
    created_at: '',
    updated_at: '',
    is_active: true,
    assets_count: 0,
    positions_count: 0,
    pending_review_positions_count: 0,
  });
  if (open.status === 'review') {
    setScreen('review');
  } else if (['uploading', 'upload_review', 'ready_to_process'].includes(open.status)) {
    setScreen('uploads');
  } else if (['processing', 'failed_processing'].includes(open.status)) {
    setScreen('processing');
  } else {
    setScreen('capture');
  }
}

function LoginScreen({
  services,
  onLoggedIn,
}: {
  services: AppServices;
  onLoggedIn: (session: AuthSession) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Shell title="Iniciar sesión">
      {error ? <ErrorText text={error} /> : null}
      <Input placeholder="Usuario" value={username} onChangeText={setUsername} />
      <Input placeholder="Contraseña" value={password} onChangeText={setPassword} secureTextEntry />
      <Button
        label={busy ? 'Ingresando...' : 'Ingresar'}
        disabled={busy || !username.trim() || !password}
        onPress={() => {
          setBusy(true);
          setError(null);
          void services.auth
            .login(username.trim(), password)
            .then(onLoggedIn)
            .catch((e) => setError(messageOf(e)))
            .finally(() => setBusy(false));
        }}
      />
    </Shell>
  );
}

function InventoriesScreen({
  services,
  localSessions,
  uploadProgress,
  onSelect,
  onOpenWork,
}: {
  services: AppServices;
  localSessions: CaptureSessionRow[];
  uploadProgress: readonly UploadSessionProgress[];
  onSelect: (i: InventoryListItemDto) => void;
  onOpenWork: (work: LocalAisleWork) => void;
}) {
  const [items, setItems] = useState<InventoryListItemDto[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    <FlatList
      data={items}
      keyExtractor={(item) => item.id}
      refreshControl={<RefreshControl refreshing={busy} onRefresh={() => load(1)} />}
      ListHeaderComponent={
        <View>
          <Text style={styles.h2}>Inventarios</Text>
          {error ? <ErrorText text={error} /> : null}
          <Input placeholder="Buscar inventario" value={search} onChangeText={setSearch} />
          <Button label="Buscar" onPress={() => load(1)} />
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
            <Button
              label="Seleccionar"
              disabled={!services.inventories.canSelect(item)}
              onPress={() => onSelect(item)}
            />
          </Card>
        );
      }}
    />
  );
}

function AislesScreen({
  services,
  inventory,
  localSessions,
  uploadProgress,
  exclusive,
  onSelectNew,
  onOpenWork,
  onBack,
  onCancelCapture,
}: {
  services: AppServices;
  inventory: InventoryListItemDto;
  localSessions: CaptureSessionRow[];
  uploadProgress: readonly UploadSessionProgress[];
  exclusive: CaptureSessionRow | null;
  onSelectNew: (a: AisleDto) => void;
  onOpenWork: (work: LocalAisleWork) => void;
  onBack: () => void;
  onCancelCapture: () => void;
}) {
  const [items, setItems] = useState<AisleDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
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

  return (
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
          <Button label="Buscar" onPress={load} />
        </View>
      }
      renderItem={({ item: aisle }) => {
        const work = workForAisle(localSessions, aisle.id, uploadProgress);
        const exclusiveOnOther =
          Boolean(exclusive) && exclusive!.aisle_id !== aisle.id && isCaptureExclusiveSession(exclusive!.status as never);
        const exclusiveHere = Boolean(exclusive) && exclusive!.aisle_id === aisle.id;
        const decision = services.aisles.evaluate(aisle, {
          exclusiveCaptureOpen: exclusiveHere,
          exclusiveCaptureOnOtherAisle: exclusiveOnOther,
        });
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
            {!decision.selectable ? (
              <ErrorText text={services.aisles.blockLabel(decision)} />
            ) : null}
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
            {exclusiveHere ? (
              <Button label="Cancelar captura" onPress={onCancelCapture} />
            ) : null}
            <Button
              label="Comenzar captura"
              disabled={!decision.selectable || Boolean(work && work.kind !== 'none' && work.kind !== 'completed')}
              onPress={() => onSelectNew(aisle)}
            />
          </Card>
        );
      }}
    />
  );
}

function CaptureScreen({
  services,
  inventory,
  aisle,
  snapshot,
  onReview,
  onBackToAisles,
  onError,
}: {
  services: AppServices;
  inventory: InventoryListItemDto | null;
  aisle: AisleDto | null;
  snapshot: CaptureSnapshot | null;
  onReview: () => void;
  onBackToAisles: () => void;
  onError: (message: string | null) => void;
}) {
  const [permission, setPermission] = useState('desconocido');
  const context = captureContextFrom(snapshot, inventory, aisle);
  const start = async () => {
    if (!inventory || !aisle) {
      throw new Error('Seleccioná inventario y pasillo para iniciar una captura nueva.');
    }
    const storage = await services.getStorageStatus();
    if (storage.lowSpace) {
      throw new Error(userMessageForCode('CAPTURE_STORAGE_LOW'));
    }
    const p = await requestPhotoPermission();
    setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
    await services.capture.start({
      inventoryId: inventory.id,
      inventoryName: inventory.name,
      aisleId: aisle.id,
      aisleName: aisle.code,
      permission: p,
    });
  };
  useEffect(() => {
    void getPhotoPermission().then((p) =>
      setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado'),
    );
  }, []);
  const photos = snapshot?.photos ?? [];
  const counts = countPhotos(photos);
  return (
    <PhotoWorkList
      photos={photos}
      onExclude={(id) => void services.capture.exclude(id)}
      onReinclude={(id) => void services.capture.reincorporate(id)}
      header={
        <View>
          <SmallButton label="← Pasillos" onPress={onBackToAisles} />
          <Text style={styles.h2}>
            Captura · {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}
          </Text>
          {snapshot?.warning ? <ErrorText text={snapshot.warning} /> : null}
          <Text style={styles.row}>Permiso fotos: {permission}</Text>
          <Text style={styles.row}>Estado: {snapshot?.session?.status ?? 'sin iniciar'}</Text>
          <Text style={styles.row}>FGS activo: {snapshot?.fgsActive ? 'sí' : 'no'}</Text>
          <Text style={styles.row}>
            Detectadas: {counts.total} · Validando: {counts.waiting} · Estables: {counts.stable} · Error:{' '}
            {counts.errors} · Excluidas: {counts.excluded}
          </Text>
          <Button
            label="Comenzar captura"
            disabled={!inventory || !aisle || Boolean(snapshot?.session)}
            onPress={() => void start().catch((e) => onError(messageOf(e)))}
          />
          <View style={styles.nav}>
            <SmallButton
              label="Escanear"
              disabled={snapshot?.session?.status !== 'active'}
              onPress={() => void services.capture.requestScan()}
            />
            <SmallButton
              label="Pausar"
              disabled={snapshot?.session?.status !== 'active'}
              onPress={() => void services.capture.pause()}
            />
            <SmallButton
              label="Reanudar"
              disabled={snapshot?.session?.status !== 'paused'}
              onPress={() =>
                void requestPhotoPermission()
                  .then((p) => {
                    setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
                    return services.capture.resume(p);
                  })
                  .catch((e) => onError(messageOf(e)))
              }
            />
          </View>
          <Button
            label="Finalizar captura"
            disabled={snapshot?.session?.status !== 'active' && snapshot?.session?.status !== 'paused'}
            onPress={() => void services.capture.finish().then(onReview).catch((e) => onError(messageOf(e)))}
          />
        </View>
      }
    />
  );
}

function ReviewScreen({
  services,
  snapshot,
  onBack,
  onDone,
  onError,
}: {
  services: AppServices;
  snapshot: CaptureSnapshot | null;
  onBack: () => void;
  onDone: (sessionId: string) => void;
  onError: (message: string | null) => void;
}) {
  const photos = snapshot?.photos ?? [];
  const counts = countPhotos(photos);
  const canConfirm = counts.waiting === 0 && counts.errors === 0;
  const context = snapshot?.context;
  return (
    <PhotoWorkList
      photos={photos}
      onExclude={(id) => void services.capture.exclude(id)}
      onReinclude={(id) => void services.capture.reincorporate(id)}
      header={
        <View>
          <SmallButton label="← Captura" onPress={onBack} />
          <Text style={styles.h2}>
            Revisión · {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}
          </Text>
          <Text style={styles.row}>
            Estables: {counts.stable} · Excluidas: {counts.excluded} · Errores: {counts.errors}
          </Text>
          {!canConfirm ? (
            <ErrorText text="Resolvé errores o esperá validaciones antes de confirmar." />
          ) : null}
          <Button
            label="Reintentar errores"
            disabled={counts.errors === 0}
            onPress={() => void services.capture.retryErrors()}
          />
          <Button
            label="Confirmar y cargar"
            disabled={!canConfirm}
            onPress={() =>
              void services.capture
                .completeReview()
                .then(onDone)
                .catch((e) => onError(messageOf(e)))
            }
          />
        </View>
      }
    />
  );
}

function UploadsScreen({
  services,
  sessionId,
  onBack,
  onProcess,
  onError,
}: {
  services: AppServices;
  sessionId: string;
  onBack: () => void;
  onProcess: () => void;
  onError: (message: string | null) => void;
}) {
  const [progress, setProgress] = useState<Awaited<
    ReturnType<AppServices['uploadQueue']['getSessionProgress']>
  > | null>(null);
  const [photos, setPhotos] = useState<CapturePhotoRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const refresh = useCallback(() => {
    void services.uploadQueue.getSessionProgress(sessionId).then(setProgress);
    void services.uploadQueue.refreshSessionReadiness(sessionId).then((r) => setReady(r === 'ready'));
  }, [services, sessionId]);
  useEffect(() => {
    refresh();
    const unsub = services.uploadQueue.subscribe(() => refresh());
    const t = setInterval(refresh, 2000);
    return () => {
      unsub();
      clearInterval(t);
    };
  }, [refresh, services]);
  useEffect(() => {
    const snap = services.capture.subscribe((s) => {
      if (s.session?.id === sessionId) setPhotos(s.photos);
    });
    void services.capture.loadSession(sessionId, false);
    return snap;
  }, [services, sessionId]);

  const uploadPhotos = photos.filter((p) => p.status === 'stable' || p.upload_status !== 'not_queued');

  return (
    <FlatList
      data={uploadPhotos}
      keyExtractor={(item) => item.id}
      numColumns={2}
      columnWrapperStyle={styles.gridRow}
      initialNumToRender={8}
      maxToRenderPerBatch={8}
      windowSize={5}
      removeClippedSubviews
      ListHeaderComponent={
        <View>
          <SmallButton label="← Pasillos" onPress={onBack} />
          <Text style={styles.h2}>
            Cargas · {progress?.inventoryName ?? ''} / {progress?.aisleName ?? ''}
          </Text>
          <Text style={styles.row}>
            Estables: {progress?.totalStable ?? 0} · Cargadas: {progress?.uploaded ?? 0} · Pendientes:{' '}
            {progress?.pending ?? 0}
          </Text>
          <View style={styles.nav}>
            <SmallButton
              label="Reintentar todo"
              onPress={() => void services.uploadQueue.retrySession(sessionId).then(refresh)}
            />
            <SmallButton label="Actualizar" onPress={refresh} />
          </View>
          <Button
            label={busy ? 'Validando...' : 'Procesar pasillo'}
            disabled={!ready || busy}
            onPress={() => {
              setBusy(true);
              void services.processing
                .startProcess(sessionId)
                .then(async (res) => {
                  if (!res.ok) {
                    onError(res.reason);
                    return;
                  }
                  if (res.jobId) await services.jobMonitor.watch(res.jobId);
                  onProcess();
                })
                .catch((e) => onError(messageOf(e)))
                .finally(() => setBusy(false));
            }}
          />
          {!ready ? (
            <Text style={styles.muted}>
              El procesamiento se habilita cuando no queden cargas pendientes ni errores recuperables.
            </Text>
          ) : null}
        </View>
      }
      ListEmptyComponent={<Text style={styles.muted}>Sin fotografías en cola.</Text>}
      renderItem={({ item: photo }) => (
        <View style={styles.photoCard}>
          <Image source={{ uri: photo.uri }} style={styles.thumb} />
          <Text style={styles.photoText} numberOfLines={1}>
            {photo.display_name}
          </Text>
          <Text style={styles.photoText}>upload: {photo.upload_status}</Text>
          {photo.upload_status === 'retryable_error' || photo.upload_status === 'permanent_error' ? (
            <SmallButton
              label="Reintentar"
              onPress={() => void services.uploadQueue.retryPhoto(photo.id).then(refresh)}
            />
          ) : null}
          {photo.upload_status === 'uploaded' ? (
            <SmallButton
              label="Excluir remoto"
              onPress={() =>
                void services.uploadQueue.excludeUploaded(sessionId, photo.id).then((r) => {
                  if (!r.ok) onError(r.reason);
                  refresh();
                })
              }
            />
          ) : (
            <SmallButton
              label="Excluir cola"
              onPress={() => void services.uploadQueue.cancelPhoto(photo.id).then(refresh)}
            />
          )}
        </View>
      )}
    />
  );
}

function ProcessingScreen({
  services,
  sessionId,
  onBack,
  onAnotherAisle,
  onError,
}: {
  services: AppServices;
  sessionId: string;
  onBack: () => void;
  onAnotherAisle: () => void;
  onError: (message: string | null) => void;
}) {
  const [jobLabel, setJobLabel] = useState('—');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const unsub = services.jobMonitor.subscribe((snap) => {
      const job = snap.jobs.find((j) => j.capture_session_id === sessionId);
      if (job) setJobLabel(String(job.remote_status ?? job.status));
    });
    return unsub;
  }, [services, sessionId]);
  return (
    <View>
      <SmallButton label="← Pasillos" onPress={onBack} />
      <Text style={styles.h2}>Procesamiento</Text>
      <Text style={styles.row}>Estado del trabajo: {jobLabel}</Text>
      <Button
        label={busy ? 'Iniciando...' : 'Iniciar / reanudar proceso'}
        disabled={busy}
        onPress={() => {
          setBusy(true);
          void services.processing
            .startProcess(sessionId)
            .then(async (res) => {
              if (!res.ok) {
                onError(res.reason);
                return;
              }
              if (res.jobId) await services.jobMonitor.watch(res.jobId);
            })
            .catch((e) => onError(messageOf(e)))
            .finally(() => setBusy(false));
        }}
      />
      <Button label="Capturar otro pasillo" onPress={onAnotherAisle} />
      <Text style={styles.muted}>
        Podés capturar otro pasillo mientras este se procesa. No se mezclan fotos ni lotes.
      </Text>
    </View>
  );
}

function PhotoWorkList({
  photos,
  onExclude,
  onReinclude,
  header,
}: {
  photos: CapturePhotoRow[];
  onExclude: (assetId: string) => void;
  onReinclude: (assetId: string) => void;
  header: React.ReactElement;
}) {
  return (
    <FlatList
      data={photos}
      keyExtractor={(item) => item.asset_id}
      numColumns={2}
      columnWrapperStyle={styles.gridRow}
      initialNumToRender={10}
      maxToRenderPerBatch={10}
      windowSize={7}
      removeClippedSubviews
      ListHeaderComponent={header}
      ListEmptyComponent={<Text style={styles.muted}>Sin fotografías.</Text>}
      renderItem={({ item: photo }) => (
        <View style={styles.photoCard}>
          <Image source={{ uri: photo.uri }} style={styles.thumb} />
          <Text style={styles.photoText} numberOfLines={1}>
            {photo.display_name}
          </Text>
          <Text style={styles.photoText}>
            [{photo.status}] {photo.width}x{photo.height}
          </Text>
          {photo.status === 'excluded' ? (
            <SmallButton label="Reincorporar" onPress={() => onReinclude(photo.asset_id)} />
          ) : (
            <SmallButton label="Excluir" onPress={() => onExclude(photo.asset_id)} />
          )}
        </View>
      )}
    />
  );
}

function DiagnosticScreen({ services, onBack }: { services: AppServices; onBack: () => void }) {
  const [checks, setChecks] = useState<readonly HealthCheckResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storageHint, setStorageHint] = useState<string | null>(null);

  const run = useCallback(() => {
    setBusy(true);
    setError(null);
    void Promise.all([services.runHealthChecks(), services.getStorageStatus()])
      .then(([results, storage]) => {
        setChecks(results);
        setStorageHint(
          storage.freeBytes == null
            ? null
            : `Libre: ${Math.round(storage.freeBytes / (1024 * 1024))} MB${storage.lowSpace ? ' (bajo)' : ''}`,
        );
      })
      .catch((e) => setError(messageOf(e)))
      .finally(() => setBusy(false));
  }, [services]);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <FlatList
      data={checks}
      keyExtractor={(c) => c.id}
      ListHeaderComponent={
        <View>
          <SmallButton label="← Inventarios" onPress={onBack} />
          <Text style={styles.h2}>Diagnóstico</Text>
          <Text style={styles.row}>
            v{services.config.versionName} ({services.config.versionCode}) · {services.config.gitSha} ·{' '}
            {services.config.environment}
          </Text>
          {storageHint ? <Text style={styles.notif}>{storageHint}</Text> : null}
          {error ? <ErrorText text={error} /> : null}
          {busy ? <ActivityIndicator color="#94d2bd" /> : null}
        </View>
      }
      renderItem={({ item: c }) => (
        <Card>
          <Text style={styles.cardTitle}>
            [{c.status}] {c.label}
          </Text>
          <Text style={styles.row}>{c.detail}</Text>
        </Card>
      )}
      ListFooterComponent={
        <View>
          <Button label="Reejecutar checks" disabled={busy} onPress={run} />
          <Button
            label="Exportar diagnóstico"
            disabled={busy}
            onPress={() => {
              setBusy(true);
              void services
                .exportDiagnostic()
                .then((bundle) =>
                  Share.share({
                    message: services.diagnosticShareText(bundle),
                    title: 'Dinamic diagnóstico',
                  }),
                )
                .catch((e) => setError(messageOf(e)))
                .finally(() => setBusy(false));
            }}
          />
          <Text style={styles.muted}>
            El export no incluye tokens, fotos ni API keys. Usalo para soporte operativo.
          </Text>
        </View>
      }
    />
  );
}

function Shell({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <View style={styles.container}>
      <Text style={styles.h1}>{title}</Text>
      <View style={styles.body}>{children}</View>
      {footer}
    </View>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

function Input(props: React.ComponentProps<typeof TextInput>) {
  return <TextInput placeholderTextColor="#94a3b8" style={styles.input} {...props} />;
}

function Button({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <TouchableOpacity style={[styles.btn, disabled && styles.btnDisabled]} disabled={disabled} onPress={onPress}>
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

function SmallButton({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <TouchableOpacity
      style={[styles.smallBtn, disabled && styles.btnDisabled]}
      disabled={disabled}
      onPress={onPress}
    >
      <Text style={styles.smallBtnText}>{label}</Text>
    </TouchableOpacity>
  );
}

function ErrorText({ text }: { text: string }) {
  return <Text style={styles.error}>{text}</Text>;
}

function countPhotos(photos: CapturePhotoRow[]) {
  return {
    total: photos.length,
    waiting: photos.filter((p) => p.status === 'detected' || p.status === 'waiting_stability').length,
    stable: photos.filter((p) => p.status === 'stable').length,
    errors: photos.filter((p) => p.status === 'unstable' || p.status === 'undecodable').length,
    excluded: photos.filter((p) => p.status === 'excluded').length,
  };
}

function captureContextFrom(
  snapshot: CaptureSnapshot | null,
  inventory: InventoryListItemDto | null,
  aisle: AisleDto | null,
): CaptureContext | null {
  if (snapshot?.context) return snapshot.context;
  if (!inventory || !aisle) return null;
  return {
    inventoryId: inventory.id,
    inventoryName: inventory.name,
    aisleId: aisle.id,
    aisleName: aisle.code,
  };
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0d1b2a', padding: 20, paddingTop: 52 },
  body: { flex: 1 },
  h1: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 12 },
  h2: { color: '#fff', fontSize: 18, fontWeight: '600', marginTop: 20, marginBottom: 8 },
  row: { color: '#e0e1dd', fontSize: 14, marginBottom: 4 },
  notif: { color: '#94d2bd', fontSize: 12, marginTop: 2 },
  error: { color: '#ff6b6b', marginBottom: 8, fontSize: 14 },
  muted: { color: '#94a3b8', marginVertical: 12 },
  input: {
    borderColor: '#3d5a80',
    borderWidth: 1,
    borderRadius: 10,
    color: '#fff',
    padding: 12,
    marginVertical: 8,
  },
  btn: {
    backgroundColor: '#1b9aaa',
    padding: 16,
    borderRadius: 12,
    marginTop: 12,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.4 },
  btnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  smallBtn: {
    backgroundColor: '#3d5a80',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    margin: 4,
  },
  smallBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  nav: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' },
  card: { borderColor: '#334155', borderWidth: 1, borderRadius: 12, padding: 12, marginVertical: 8 },
  cardTitle: { color: '#fff', fontWeight: '700', fontSize: 16, marginBottom: 4 },
  pendingBox: { marginTop: 8, marginBottom: 4 },
  gridRow: { justifyContent: 'space-between', gap: 8, marginBottom: 8 },
  photoCard: { width: '48%', borderColor: '#334155', borderWidth: 1, borderRadius: 10, padding: 8 },
  thumb: { width: '100%', height: 120, borderRadius: 8, backgroundColor: '#1e293b' },
  photoText: { color: '#cbd5e1', fontSize: 11, marginTop: 4 },
});
