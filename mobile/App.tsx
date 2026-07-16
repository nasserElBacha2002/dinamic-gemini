/**
 * Fase 0 spike screen — corrected: stability, serialized scans, dual cursors, FGS lifecycle.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import {
  compareCursor,
  cursorFromMarker,
  EMPTY_CURSOR,
  type CompositeCursor,
} from './src/core/compositeCursor';
import { upsertByAssetId } from './src/core/dedupe';
import { createLogger } from './src/core/logging';
import { detectNewPhotos } from './src/core/photoDetection';
import { createScanCoordinator } from './src/core/scanCoordinator';
import type { CaptureMarker } from './src/domain/entities/captureMarker';
import type { GalleryImage } from './src/domain/entities/galleryImage';
import type { SpikePhotoStatus } from './src/domain/enums/photoStatus';
import {
  buildCaptureNotificationText,
  createForegroundService,
  type ForegroundService,
} from './src/native/foregroundService';
import {
  getPhotoPermission,
  queryMostRecentPhoto,
  queryNewPhotosSince,
  requestPhotoPermission,
  subscribeToGalleryChanges,
} from './src/native/mediaStore';
import { probeStability } from './src/native/stabilityProber';
import type { ScanMetrics } from './src/core/incrementalScan';
import { emptyScanMetrics } from './src/core/incrementalScan';

const log = createLogger();
const SPIKE_CONTEXT = { inventoryId: 'spike-inv', aisleId: 'spike-aisle' };

interface SpikePhoto {
  readonly assetId: string;
  readonly image: GalleryImage;
  readonly status: SpikePhotoStatus;
}

type SessionPhase = 'idle' | 'active' | 'finished';

export default function App(): JSX.Element {
  const fgsRef = useRef<ForegroundService>(createForegroundService());
  const [permission, setPermission] = useState<string>('desconocido');
  const [session, setSession] = useState<SessionPhase>('idle');
  const [marker, setMarker] = useState<CaptureMarker | null>(null);
  const [photos, setPhotos] = useState<SpikePhoto[]>([]);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [scanCursor, setScanCursor] = useState<CompositeCursor>(EMPTY_CURSOR);
  const [lastValidCursor, setLastValidCursor] = useState<CompositeCursor>(EMPTY_CURSOR);
  const [scanInProgress, setScanInProgress] = useState(false);
  const [pendingEvents, setPendingEvents] = useState(false);
  const [fgsActive, setFgsActive] = useState(false);
  const [lastMetrics, setLastMetrics] = useState<ScanMetrics>(emptyScanMetrics());
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  const scanCursorRef = useRef<CompositeCursor>(EMPTY_CURSOR);
  const lastValidRef = useRef<CompositeCursor>(EMPTY_CURSOR);
  const inspectedRef = useRef<Set<string>>(new Set());
  const sessionRef = useRef<SessionPhase>('idle');
  const stabilityAbortRef = useRef(false);
  const photosRef = useRef<SpikePhoto[]>([]);

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const refreshPermission = useCallback(async () => {
    const p = await getPhotoPermission();
    setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
    return p;
  }, []);

  useEffect(() => {
    void refreshPermission();
  }, [refreshPermission]);

  const counts = useMemo(() => {
    let waiting = 0;
    let stable = 0;
    let unstable = 0;
    let undecodable = 0;
    for (const p of photos) {
      if (p.status === 'waiting_stability') waiting += 1;
      else if (p.status === 'stable') stable += 1;
      else if (p.status === 'unstable') unstable += 1;
      else if (p.status === 'undecodable') undecodable += 1;
    }
    return { waiting, stable, unstable, undecodable, detected: photos.length };
  }, [photos]);

  const pushFgsUpdate = useCallback(async () => {
    if (!fgsRef.current.isAvailable || !fgsActive) return;
    await fgsRef.current.update({
      inventoryName: 'Spike',
      aisleName: 'Aisle',
      detected: photosRef.current.length,
      stable: photosRef.current.filter((p) => p.status === 'stable').length,
      pending: photosRef.current.filter((p) => p.status === 'waiting_stability').length,
    });
  }, [fgsActive]);

  const runStability = useCallback(
    async (image: GalleryImage) => {
      if (stabilityAbortRef.current || sessionRef.current !== 'active') return;
      const outcome = await probeStability(image.uri, { intervalMs: 750 });
      if (stabilityAbortRef.current) return;

      setPhotos((prev) => {
        const status: SpikePhotoStatus = outcome.ok
          ? 'stable'
          : outcome.reason === 'undecodable'
            ? 'undecodable'
            : 'unstable';
        const next = upsertByAssetId(prev, {
          assetId: image.assetId,
          image,
          status,
        });
        return next;
      });

      if (outcome.ok) {
        const nextValid: CompositeCursor = {
          dateAdded: image.dateAdded,
          assetId: image.assetId,
        };
        if (compareCursor(nextValid, lastValidRef.current) > 0) {
          lastValidRef.current = nextValid;
          setLastValidCursor(nextValid);
        }
        log.info('photo_detected', { assetId: image.assetId, status: 'stable' });
      } else {
        log.warn('file_unstable', { assetId: image.assetId, reason: outcome.reason });
      }
      void pushFgsUpdate();
    },
    [pushFgsUpdate],
  );

  const runScanOnce = useCallback(async () => {
    if (sessionRef.current !== 'active') return;
    setScanInProgress(true);
    try {
      const { images, metrics } = await queryNewPhotosSince({
        scanCursor: scanCursorRef.current,
        pageSize: 50,
      });
      setLastMetrics(metrics);
      log.info('photo_detected', {
        event: 'scan_metrics',
        ...metrics,
      });

      const result = detectNewPhotos({
        candidates: images,
        scanCursor: scanCursorRef.current,
        inspectedIds: inspectedRef.current,
      });

      for (const id of result.inspectedIds) {
        inspectedRef.current.add(id);
      }
      scanCursorRef.current = result.nextScanCursor;
      setScanCursor(result.nextScanCursor);

      if (result.rejected.length) {
        setRejectedCount((c) => c + result.rejected.length);
        result.rejected.forEach((r) =>
          log.info('photo_ignored', { assetId: r.assetId, reason: r.reason, layer: 'core_defensive' }),
        );
      }

      if (result.admitted.length) {
        setPhotos((prev) => {
          let next = prev;
          for (const img of result.admitted) {
            next = upsertByAssetId(next, {
              assetId: img.assetId,
              image: img,
              status: 'waiting_stability',
            });
          }
          return next;
        });
        for (const img of result.admitted) {
          void runStability(img);
        }
      }
      void pushFgsUpdate();
    } catch (e) {
      setErrorBanner(e instanceof Error ? e.message : 'Error de scan');
      log.error('error', { where: 'scan', message: String(e) });
    } finally {
      setScanInProgress(false);
      setPendingEvents(false);
    }
  }, [pushFgsUpdate, runStability]);

  const coordinatorRef = useRef(createScanCoordinator(runScanOnce));
  useEffect(() => {
    coordinatorRef.current = createScanCoordinator(runScanOnce);
  }, [runScanOnce]);

  const requestScan = useCallback(() => {
    if (sessionRef.current !== 'active') return;
    if (coordinatorRef.current.isInProgress) {
      setPendingEvents(true);
    }
    void coordinatorRef.current.request();
  }, []);

  const stopSession = useCallback(async () => {
    stabilityAbortRef.current = true;
    setSession('finished');
    sessionRef.current = 'finished';
    try {
      await fgsRef.current.stop();
    } catch (e) {
      log.error('error', { where: 'fgs_stop', message: String(e) });
    }
    setFgsActive(false);
    log.info('session_finish', {
      stable: photosRef.current.filter((p) => p.status === 'stable').length,
      total: photosRef.current.length,
    });
  }, []);

  const startSession = useCallback(async () => {
    setErrorBanner(null);
    const perm = await requestPhotoPermission();
    setPermission(perm.granted ? (perm.limited ? 'parcial' : 'completo') : 'denegado');
    if (!perm.granted) {
      setErrorBanner('Se necesitan permisos de fotografías');
      return;
    }

    stabilityAbortRef.current = false;
    const recent = await queryMostRecentPhoto();
    const m: CaptureMarker = {
      assetId: recent?.assetId ?? null,
      mediaStoreNumericId: recent?.mediaStoreNumericId ?? null,
      dateAdded: recent?.dateAdded ?? null,
      dateModified: recent?.dateModified ?? null,
      displayName: recent?.displayName ?? null,
      size: recent?.size ?? null,
      bucketId: recent?.bucketId ?? null,
      inventoryId: SPIKE_CONTEXT.inventoryId,
      aisleId: SPIKE_CONTEXT.aisleId,
    };
    const initial = cursorFromMarker(m);
    setMarker(m);
    scanCursorRef.current = initial;
    lastValidRef.current = initial;
    setScanCursor(initial);
    setLastValidCursor(initial);
    inspectedRef.current = new Set(recent?.assetId ? [recent.assetId] : []);
    setPhotos([]);
    setRejectedCount(0);
    setLastMetrics(emptyScanMetrics());
    setSession('active');
    sessionRef.current = 'active';

    log.info('marker_initial', {
      assetId: m.assetId,
      dateAdded: m.dateAdded,
      fgsAvailable: fgsRef.current.isAvailable,
    });

    try {
      await fgsRef.current.start({
        inventoryName: 'Spike',
        aisleName: 'Aisle',
        detected: 0,
        stable: 0,
        pending: 0,
      });
      setFgsActive(fgsRef.current.isAvailable);
      if (!fgsRef.current.isAvailable) {
        setErrorBanner('Foreground Service no disponible en este runtime (¿falta rebuild nativo?)');
      }
    } catch (e) {
      setFgsActive(false);
      setErrorBanner(`No se pudo iniciar FGS: ${e instanceof Error ? e.message : String(e)}`);
      log.error('error', { where: 'fgs_start', message: String(e) });
    }
  }, []);

  const clearResults = useCallback(() => {
    if (session === 'active') return;
    setPhotos([]);
    setRejectedCount(0);
    setMarker(null);
    setScanCursor(EMPTY_CURSOR);
    setLastValidCursor(EMPTY_CURSOR);
    setLastMetrics(emptyScanMetrics());
    setSession('idle');
    sessionRef.current = 'idle';
    setErrorBanner(null);
  }, [session]);

  const retryUnstable = useCallback(() => {
    const targets = photosRef.current.filter(
      (p) => p.status === 'unstable' || p.status === 'undecodable',
    );
    for (const t of targets) {
      setPhotos((prev) =>
        upsertByAssetId(prev, {
          assetId: t.assetId,
          image: t.image,
          status: 'waiting_stability',
        }),
      );
      void runStability(t.image);
    }
  }, [runStability]);

  useEffect(() => {
    if (session !== 'active') return;
    const sub = subscribeToGalleryChanges(() => requestScan());
    return () => sub.remove();
  }, [session, requestScan]);

  useEffect(() => {
    const fgs = fgsRef.current;
    return () => {
      stabilityAbortRef.current = true;
      void fgs.stop();
    };
  }, []);

  const notifPreview = useMemo(
    () =>
      buildCaptureNotificationText({
        inventoryName: 'Spike',
        aisleName: 'Aisle',
        detected: counts.detected,
        stable: counts.stable,
        pending: counts.waiting,
      }),
    [counts],
  );

  const fgsAvailable = fgsRef.current.isAvailable;

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.h1}>Spike captura (solo fotografías)</Text>
        {errorBanner ? <Text style={styles.error}>{errorBanner}</Text> : null}

        <Text style={styles.row}>Permiso: {permission}</Text>
        <Text style={styles.row}>Sesión: {session}</Text>
        <Text style={styles.row}>FGS disponible: {fgsAvailable ? 'sí' : 'no'}</Text>
        <Text style={styles.row}>FGS activo: {fgsActive ? 'sí' : 'no'}</Text>
        <Text style={styles.row}>
          Marcador: {marker ? `${marker.assetId ?? '∅'} @ ${marker.dateAdded ?? '∅'}` : '—'}
        </Text>
        <Text style={styles.row}>
          Scan cursor: {scanCursor.assetId || '∅'} @ {scanCursor.dateAdded}
        </Text>
        <Text style={styles.row}>
          Última válida: {lastValidCursor.assetId || '∅'} @ {lastValidCursor.dateAdded}
        </Text>
        <Text style={styles.row}>
          Scan: {scanInProgress ? 'activo' : 'idle'}
          {pendingEvents ? ' · eventos pendientes' : ''}
        </Text>
        <Text style={styles.row}>
          Esperando estabilidad: {counts.waiting} · Estables: {counts.stable}
        </Text>
        <Text style={styles.row}>
          Inestables: {counts.unstable} · No decodificables: {counts.undecodable}
        </Text>
        <Text style={styles.row}>
          Rechazadas (defensa core): {rejectedCount}
        </Text>
        <Text style={styles.row}>
          Último scan: {lastMetrics.durationMs}ms · páginas {lastMetrics.pagesQueried} · leídos{' '}
          {lastMetrics.assetsRead} · hidratados {lastMetrics.assetsHydrated}
        </Text>
        <Text style={styles.notif}>{notifPreview.title}</Text>
        <Text style={styles.notif}>{notifPreview.body}</Text>

        <TouchableOpacity style={styles.btn} onPress={() => void refreshPermission().then((p) => {
          if (!p.granted) void requestPhotoPermission().then(refreshPermission);
        })}>
          <Text style={styles.btnText}>Solicitar permisos</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, session === 'active' && styles.btnDisabled]}
          disabled={session === 'active'}
          onPress={() => void startSession()}
        >
          <Text style={styles.btnText}>Marcar inicio</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.btnSecondary, session !== 'active' && styles.btnDisabled]}
          disabled={session !== 'active'}
          onPress={requestScan}
        >
          <Text style={styles.btnText}>Escanear</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.btnWarn, session !== 'active' && styles.btnDisabled]}
          disabled={session !== 'active'}
          onPress={() => void stopSession()}
        >
          <Text style={styles.btnText}>Finalizar captura</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.btnSecondary, session === 'active' && styles.btnDisabled]}
          disabled={session === 'active' || (counts.unstable + counts.undecodable === 0)}
          onPress={retryUnstable}
        >
          <Text style={styles.btnText}>Reintentar inestables</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.btnSecondary, session === 'active' && styles.btnDisabled]}
          disabled={session === 'active'}
          onPress={clearResults}
        >
          <Text style={styles.btnText}>Limpiar resultados</Text>
        </TouchableOpacity>

        {scanInProgress ? <ActivityIndicator color="#94d2bd" style={{ marginTop: 12 }} /> : null}

        <Text style={styles.h2}>Fotografías</Text>
        {photos.map((p) => (
          <Text key={p.assetId} style={styles.item}>
            [{p.status}] {p.image.displayName} · {p.image.mimeType} · {p.image.width}x
            {p.image.height}
          </Text>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0d1b2a' },
  content: { padding: 24, paddingTop: 56, paddingBottom: 48 },
  h1: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 12 },
  h2: { color: '#fff', fontSize: 18, fontWeight: '600', marginTop: 20, marginBottom: 8 },
  row: { color: '#e0e1dd', fontSize: 14, marginBottom: 4 },
  notif: { color: '#94d2bd', fontSize: 12, marginTop: 2 },
  error: { color: '#ff6b6b', marginBottom: 8, fontSize: 14 },
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
  item: { color: '#adb5bd', fontSize: 12, paddingVertical: 3 },
});
