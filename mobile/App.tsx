import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  RefreshControl,
  ScrollView,
  StyleSheet,
  TextInput,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import type { AppServices } from './src/app/bootstrap/createAppServices';
import { createAppServices } from './src/app/bootstrap/createAppServices';
import type { CaptureContext, CaptureSnapshot } from './src/features/capture/captureService';
import type { AuthSession } from './src/features/auth/authService';
import type { AisleDto, InventoryListItemDto } from './src/services/api/types';
import { getPhotoPermission, requestPhotoPermission } from './src/native/mediaStore';
import type { CapturePhotoRow } from './src/database/schema/captureSchema';

type Screen = 'login' | 'inventories' | 'aisles' | 'activity' | 'capture' | 'review';

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

  useEffect(() => {
    let mounted = true;
    let unsubscribeCapture: (() => void) | undefined;
    let createdServices: AppServices | undefined;
    void createAppServices(() => {
      setAuth(null);
      setScreen('login');
    }).then(async (created) => {
      if (!mounted) return;
      createdServices = created;
      setServices(created);
      setConfigError(created.configError);
      const restored = created.configError ? null : await created.auth.restore();
      if (!mounted) return;
      setAuth(restored);
      const open = await created.capture.restoreLatestOpen();
      unsubscribeCapture = created.capture.subscribe((snapshot) => {
        if (mounted) {
          setCapture(snapshot);
        }
      });
      if (restored) {
        setScreen(open ? (open.status === 'review' ? 'review' : 'activity') : 'inventories');
      }
      setLoading(false);
    }).catch((e) => {
      setError(messageOf(e));
      setLoading(false);
    });
    return () => {
      mounted = false;
      unsubscribeCapture?.();
      createdServices?.capture.dispose();
    };
  }, []);

  if (loading || !services) {
    return <Shell title="Dinamic Captura"><ActivityIndicator color="#94d2bd" /></Shell>;
  }

  if (configError) {
    return <Shell title="Configuración"><ErrorText text={configError} /></Shell>;
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

  return (
    <Shell
      title="Dinamic Captura"
      footer={
        <View style={styles.nav}>
          <SmallButton label="Inventarios" onPress={() => setScreen('inventories')} />
          <SmallButton label="Sesiones" onPress={() => setScreen('activity')} />
          <SmallButton label="Salir" onPress={() => void services.auth.logout().finally(() => setAuth(null))} />
        </View>
      }
    >
      {error ? <ErrorText text={error} /> : null}
      {screen === 'inventories' ? (
        <InventoriesScreen
          services={services}
          onSelect={(inventory) => {
            setSelectedInventory(inventory);
            setScreen('aisles');
          }}
        />
      ) : null}
      {screen === 'aisles' && selectedInventory ? (
        <AislesScreen
          services={services}
          inventory={selectedInventory}
          onBack={() => setScreen('inventories')}
          onSelect={(aisle) => {
            setSelectedAisle(aisle);
            setScreen('capture');
          }}
        />
      ) : null}
      {screen === 'activity' ? (
        <ActivityScreen
          capture={capture}
          onOpen={() => setScreen(capture?.session?.status === 'review' ? 'review' : 'capture')}
          onCancel={() => void services.capture.cancel()}
        />
      ) : null}
      {screen === 'capture' && (capture?.context || (selectedInventory && selectedAisle)) ? (
        <CaptureScreen
          services={services}
          inventory={selectedInventory}
          aisle={selectedAisle}
          snapshot={capture}
          onReview={() => setScreen('review')}
          onError={setError}
        />
      ) : null}
      {screen === 'review' ? (
        <ReviewScreen
          services={services}
          snapshot={capture}
          onBack={() => setScreen('capture')}
          onDone={() => setScreen('activity')}
          onError={setError}
        />
      ) : null}
    </Shell>
  );
}

function LoginScreen({ services, onLoggedIn }: { services: AppServices; onLoggedIn: (session: AuthSession) => void }) {
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
          void services.auth.login(username.trim(), password).then(onLoggedIn).catch((e) => setError(messageOf(e))).finally(() => setBusy(false));
        }}
      />
    </Shell>
  );
}

function InventoriesScreen({ services, onSelect }: { services: AppServices; onSelect: (i: InventoryListItemDto) => void }) {
  const [items, setItems] = useState<InventoryListItemDto[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const load = useCallback((nextPage = page) => {
    setBusy(true);
    setError(null);
    void services.inventories.list({ search, page: nextPage }).then((res) => {
      setItems(res.items);
      setPage(res.page);
      setTotalPages(Math.max(1, res.total_pages));
    }).catch((e) => setError(messageOf(e))).finally(() => setBusy(false));
  }, [page, search, services]);
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    load(1);
  }, [load]);
  return (
    <ScrollView refreshControl={<RefreshControl refreshing={busy} onRefresh={() => load(1)} />}>
      <Text style={styles.h2}>Inventarios</Text>
      {error ? <ErrorText text={error} /> : null}
      <Input placeholder="Buscar inventario" value={search} onChangeText={setSearch} />
      <Button label="Buscar" onPress={() => load(1)} />
      {items.length === 0 && !busy ? <Text style={styles.muted}>Sin inventarios.</Text> : null}
      {items.map((item) => (
        <Card key={item.id}>
          <Text style={styles.cardTitle}>{item.name}</Text>
          <Text style={styles.row}>Estado: {item.status} · Pasillos: {item.aisles_count}</Text>
          <Button label="Seleccionar" disabled={!services.inventories.canSelect(item)} onPress={() => onSelect(item)} />
        </Card>
      ))}
      <View style={styles.nav}>
        <SmallButton label="Anterior" disabled={page <= 1} onPress={() => load(page - 1)} />
        <Text style={styles.row}>Página {page}/{totalPages}</Text>
        <SmallButton label="Siguiente" disabled={page >= totalPages} onPress={() => load(page + 1)} />
      </View>
    </ScrollView>
  );
}

function AislesScreen({ services, inventory, onSelect, onBack }: { services: AppServices; inventory: InventoryListItemDto; onSelect: (a: AisleDto) => void; onBack: () => void }) {
  const [items, setItems] = useState<AisleDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const loadedRef = useRef(false);
  const load = useCallback(() => {
    setBusy(true);
    void services.aisles.list({ inventoryId: inventory.id, search }).then((res) => setItems(res.items)).catch((e) => setError(messageOf(e))).finally(() => setBusy(false));
  }, [inventory.id, search, services]);
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    load();
  }, [load]);
  return (
    <ScrollView refreshControl={<RefreshControl refreshing={busy} onRefresh={load} />}>
      <SmallButton label="← Inventarios" onPress={onBack} />
      <Text style={styles.h2}>Pasillos · {inventory.name}</Text>
      {error ? <ErrorText text={error} /> : null}
      <Input placeholder="Buscar pasillo" value={search} onChangeText={setSearch} />
      <Button label="Buscar" onPress={load} />
      {items.map((aisle) => (
        <Card key={aisle.id}>
          <Text style={styles.cardTitle}>{aisle.code}</Text>
          <Text style={styles.row}>Estado: {aisle.status} · Activo: {aisle.is_active ? 'sí' : 'no'}</Text>
          <Text style={styles.row}>Fotos existentes: {aisle.assets_count} · Job: {aisle.latest_job?.status ?? '—'}</Text>
          <Button label="Comenzar captura" disabled={!services.aisles.canSelect(aisle)} onPress={() => onSelect(aisle)} />
        </Card>
      ))}
    </ScrollView>
  );
}

function CaptureScreen({ services, inventory, aisle, snapshot, onReview, onError }: { services: AppServices; inventory: InventoryListItemDto | null; aisle: AisleDto | null; snapshot: CaptureSnapshot | null; onReview: () => void; onError: (message: string | null) => void }) {
  const [permission, setPermission] = useState('desconocido');
  const context = captureContextFrom(snapshot, inventory, aisle);
  const start = async () => {
    if (!inventory || !aisle) {
      throw new Error('Seleccioná inventario y pasillo para iniciar una captura nueva.');
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
    void getPhotoPermission().then((p) => setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado'));
  }, []);
  const counts = countPhotos(snapshot?.photos ?? []);
  return (
    <ScrollView>
      <Text style={styles.h2}>Captura · {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}</Text>
      {snapshot?.warning ? <ErrorText text={snapshot.warning} /> : null}
      <Text style={styles.row}>Permiso fotos: {permission}</Text>
      <Text style={styles.row}>Sesión: {snapshot?.session?.status ?? 'sin iniciar'}</Text>
      <Text style={styles.row}>FGS activo: {snapshot?.fgsActive ? 'sí' : 'no'}</Text>
      <Text style={styles.row}>Scan: {snapshot?.scanInProgress ? 'activo' : 'idle'} {snapshot?.pendingScan ? '· pendiente' : ''}</Text>
      <Text style={styles.row}>Detectadas: {counts.total} · Validando: {counts.waiting} · Estables: {counts.stable} · Error: {counts.errors} · Excluidas: {counts.excluded}</Text>
      <Text style={styles.row}>Validaciones activas: {snapshot?.activeValidations ?? 0}</Text>
      <Text style={styles.row}>Scan cursor: {snapshot?.scanCursor.assetId || '∅'} @ {snapshot?.scanCursor.dateAdded ?? -1}</Text>
      <Text style={styles.row}>Última válida: {snapshot?.lastValidCursor.assetId || '∅'} @ {snapshot?.lastValidCursor.dateAdded ?? -1}</Text>
      <Text style={styles.row}>Último scan: {snapshot?.metrics.durationMs ?? 0}ms · leídos {snapshot?.metrics.assetsRead ?? 0} · hidratados {snapshot?.metrics.assetsHydrated ?? 0}</Text>
      <Button label="Comenzar captura" disabled={!inventory || !aisle || Boolean(snapshot?.session)} onPress={() => void start().catch((e) => onError(messageOf(e)))} />
      <View style={styles.nav}>
        <SmallButton label="Escanear" disabled={snapshot?.session?.status !== 'active'} onPress={() => void services.capture.requestScan()} />
        <SmallButton label="Pausar" disabled={snapshot?.session?.status !== 'active'} onPress={() => void services.capture.pause()} />
        <SmallButton
          label="Reanudar"
          disabled={snapshot?.session?.status !== 'paused'}
          onPress={() => void requestPhotoPermission()
            .then((p) => {
              setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
              return services.capture.resume(p);
            })
            .catch((e) => onError(messageOf(e)))}
        />
      </View>
      <Button label="Finalizar captura" disabled={snapshot?.session?.status !== 'active' && snapshot?.session?.status !== 'paused'} onPress={() => void services.capture.finish().then(onReview).catch((e) => onError(messageOf(e)))} />
      <PhotoGrid photos={snapshot?.photos ?? []} onExclude={(id) => void services.capture.exclude(id)} onReinclude={(id) => void services.capture.reincorporate(id)} />
    </ScrollView>
  );
}

function ReviewScreen({ services, snapshot, onBack, onDone, onError }: { services: AppServices; snapshot: CaptureSnapshot | null; onBack: () => void; onDone: () => void; onError: (message: string | null) => void }) {
  const counts = countPhotos(snapshot?.photos ?? []);
  const canConfirm = counts.waiting === 0 && counts.errors === 0;
  const context = snapshot?.context;
  return (
    <ScrollView>
      <SmallButton label="← Captura" onPress={onBack} />
      <Text style={styles.h2}>Revisión · {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}</Text>
      <Text style={styles.row}>Estables: {counts.stable} · Excluidas: {counts.excluded} · Errores: {counts.errors}</Text>
      {!canConfirm ? <ErrorText text="Resolvé errores o esperá validaciones antes de confirmar." /> : null}
      <Button label="Reintentar errores" disabled={counts.errors === 0} onPress={() => void services.capture.retryErrors()} />
      <Button label="Confirmar sesión" disabled={!canConfirm} onPress={() => void services.capture.completeReview().then(onDone).catch((e) => onError(messageOf(e)))} />
      <PhotoGrid photos={snapshot?.photos ?? []} onExclude={(id) => void services.capture.exclude(id)} onReinclude={(id) => void services.capture.reincorporate(id)} />
    </ScrollView>
  );
}

function ActivityScreen({ capture, onOpen, onCancel }: { capture: CaptureSnapshot | null; onOpen: () => void; onCancel: () => void }) {
  if (!capture?.session) {
    return <Text style={styles.muted}>No hay sesiones pendientes.</Text>;
  }
  const counts = countPhotos(capture.photos);
  return (
    <Card>
      <Text style={styles.cardTitle}>{capture.session.inventory_name} · {capture.session.aisle_name}</Text>
      <Text style={styles.row}>Estado: {capture.session.status}</Text>
      <Text style={styles.row}>Fotos: {counts.total} · Estables: {counts.stable} · Errores: {counts.errors}</Text>
      <Button label="Abrir" onPress={onOpen} />
      <Button label="Cancelar sesión local" onPress={() => Alert.alert('Cancelar', 'No se borran fotos del teléfono.', [{ text: 'No' }, { text: 'Cancelar', style: 'destructive', onPress: onCancel }])} />
    </Card>
  );
}

function PhotoGrid({ photos, onExclude, onReinclude }: { photos: CapturePhotoRow[]; onExclude: (assetId: string) => void; onReinclude: (assetId: string) => void }) {
  return (
    <View style={styles.grid}>
      {photos.map((photo) => (
        <View key={photo.asset_id} style={styles.photoCard}>
          <Image source={{ uri: photo.uri }} style={styles.thumb} />
          <Text style={styles.photoText}>{photo.display_name}</Text>
          <Text style={styles.photoText}>[{photo.status}] {photo.width}x{photo.height}</Text>
          {photo.status === 'excluded' ? (
            <SmallButton label="Reincorporar" onPress={() => onReinclude(photo.asset_id)} />
          ) : (
            <SmallButton label="Excluir" onPress={() => onExclude(photo.asset_id)} />
          )}
        </View>
      ))}
    </View>
  );
}

function Shell({ title, children, footer }: { title: string; children: React.ReactNode; footer?: React.ReactNode }) {
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

function Button({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <TouchableOpacity style={[styles.btn, disabled && styles.btnDisabled]} disabled={disabled} onPress={onPress}>
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

function SmallButton({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <TouchableOpacity style={[styles.smallBtn, disabled && styles.btnDisabled]} disabled={disabled} onPress={onPress}>
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
  if (snapshot?.context) {
    return snapshot.context;
  }
  if (!inventory || !aisle) {
    return null;
  }
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
  content: { paddingBottom: 48 },
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
  btnSecondary: { backgroundColor: '#3d5a80' },
  btnWarn: { backgroundColor: '#9b2226' },
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
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  photoCard: { width: '48%', borderColor: '#334155', borderWidth: 1, borderRadius: 10, padding: 8 },
  thumb: { width: '100%', height: 120, borderRadius: 8, backgroundColor: '#1e293b' },
  photoText: { color: '#cbd5e1', fontSize: 11, marginTop: 4 },
  item: { color: '#adb5bd', fontSize: 12, paddingVertical: 3 },
});
