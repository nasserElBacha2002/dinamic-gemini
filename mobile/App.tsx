/**
 * Fase 0 spike screen — Android MediaStore capture viability.
 *
 * Manual test harness (run on a real device via a Development Build):
 *   1. Grant photos-only permission (no video prompt).
 *   2. Tap "Marcar inicio" to freeze the composite marker (last existing photo).
 *   3. Take/copy ~20 photos (and one .mp4) into the gallery, screen locked between shots.
 *   4. Tap "Escanear" (or rely on the gallery listener) to detect NEW photos only.
 *   5. Verify: 20 photos detected, the video ignored, marker unaffected by the video.
 *
 * This screen exercises the real device path; the correctness logic it calls is the same
 * pure-core covered by the unit tests.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { cursorFromMarker, type CompositeCursor } from './src/core/compositeCursor';
import { detectNewPhotos } from './src/core/photoDetection';
import { createLogger } from './src/core/logging';
import type { CaptureMarker } from './src/domain/entities/captureMarker';
import type { GalleryImage } from './src/domain/entities/galleryImage';
import {
  buildCaptureNotificationText,
  noopForegroundService,
} from './src/native/foregroundService';
import {
  queryMostRecentPhoto,
  queryPhotos,
  requestPhotoPermission,
  subscribeToGalleryChanges,
} from './src/native/mediaStore';

const log = createLogger();

const SPIKE_CONTEXT = { inventoryId: 'spike-inv', aisleId: 'spike-aisle' };

export default function App(): JSX.Element {
  const [permission, setPermission] = useState<string>('desconocido');
  const [marker, setMarker] = useState<CaptureMarker | null>(null);
  const [detected, setDetected] = useState<GalleryImage[]>([]);
  const [ignored, setIgnored] = useState<number>(0);
  const cursorRef = useRef<CompositeCursor>({ dateAdded: -1, mediaStoreId: -1 });
  const seenRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    void requestPhotoPermission().then((p) => {
      setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
      log.info('session_start', { permission: p.granted, limited: p.limited });
    });
  }, []);

  const startMarker = useCallback(async () => {
    const recent = await queryMostRecentPhoto();
    const m: CaptureMarker = {
      mediaStoreId: recent?.mediaStoreId ?? null,
      dateAdded: recent?.dateAdded ?? null,
      dateModified: recent?.dateModified ?? null,
      displayName: recent?.displayName ?? null,
      size: recent?.size ?? null,
      bucketId: recent?.bucketId ?? null,
      inventoryId: SPIKE_CONTEXT.inventoryId,
      aisleId: SPIKE_CONTEXT.aisleId,
    };
    setMarker(m);
    cursorRef.current = cursorFromMarker(m);
    seenRef.current = new Set();
    setDetected([]);
    setIgnored(0);
    log.info('marker_initial', { mediaStoreId: m.mediaStoreId, dateAdded: m.dateAdded });

    if (noopForegroundService.isAvailable) {
      await noopForegroundService.start({
        inventoryName: 'Spike',
        aisleName: 'Aisle',
        detected: 0,
        pending: 0,
        uploaded: 0,
      });
    } else {
      log.warn('error', { fgs: 'unavailable_in_runtime' });
    }
  }, []);

  const scan = useCallback(async () => {
    let after: string | undefined;
    const collectedNew: GalleryImage[] = [];
    let ignoredCount = 0;
    // Paginate the whole photos collection; pure-core decides what is new + admissible.
    for (;;) {
      const page = await queryPhotos({ pageSize: 200, ...(after ? { after } : {}) });
      const result = detectNewPhotos({
        candidates: page.images,
        cursor: cursorRef.current,
        seenIds: seenRef.current,
      });
      collectedNew.push(...result.newPhotos);
      ignoredCount += result.rejected.length;
      for (const id of result.seenAdditions) {
        seenRef.current.add(id);
      }
      cursorRef.current = result.nextCursor;
      result.rejected.forEach((r) =>
        log.info('photo_ignored', { mediaStoreId: r.mediaStoreId, reason: r.reason }),
      );
      if (!page.hasNextPage) {
        break;
      }
      after = page.endCursor;
    }
    setDetected((prev) => [...prev, ...collectedNew]);
    setIgnored((prev) => prev + ignoredCount);
    collectedNew.forEach((p) =>
      log.info('photo_detected', { mediaStoreId: p.mediaStoreId, mime: p.mimeType }),
    );
  }, []);

  useEffect(() => {
    if (!marker) {
      return;
    }
    const sub = subscribeToGalleryChanges(() => void scan());
    return () => sub.remove();
  }, [marker, scan]);

  const notif = useMemo(
    () =>
      buildCaptureNotificationText({
        inventoryName: 'Spike',
        aisleName: 'Aisle',
        detected: detected.length,
        pending: detected.length,
        uploaded: 0,
      }),
    [detected.length],
  );

  return (
    <View style={styles.container}>
      <Text style={styles.h1}>Spike captura (solo fotografías)</Text>
      <Text style={styles.row}>Permiso de fotos: {permission}</Text>
      <Text style={styles.row}>
        Marcador: {marker ? `id=${marker.mediaStoreId ?? '∅'} date=${marker.dateAdded ?? '∅'}` : 'sin marcar'}
      </Text>
      <Text style={styles.row}>Nuevas detectadas: {detected.length}</Text>
      <Text style={styles.row}>Ignoradas (no imagen): {ignored}</Text>
      <Text style={styles.notif}>{notif.title}</Text>
      <Text style={styles.notif}>{notif.body}</Text>

      <TouchableOpacity style={styles.btn} onPress={() => void startMarker()}>
        <Text style={styles.btnText}>Marcar inicio</Text>
      </TouchableOpacity>
      <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={() => void scan()}>
        <Text style={styles.btnText}>Escanear</Text>
      </TouchableOpacity>

      <ScrollView style={styles.list}>
        {detected.map((p) => (
          <Text key={p.mediaStoreId} style={styles.item}>
            {p.displayName} · {p.mimeType} · {p.width}x{p.height}
          </Text>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, paddingTop: 64, backgroundColor: '#0d1b2a' },
  h1: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 16 },
  row: { color: '#e0e1dd', fontSize: 16, marginBottom: 6 },
  notif: { color: '#94d2bd', fontSize: 13, marginTop: 4 },
  btn: {
    backgroundColor: '#1b9aaa',
    padding: 18,
    borderRadius: 12,
    marginTop: 16,
    alignItems: 'center',
  },
  btnSecondary: { backgroundColor: '#3d5a80' },
  btnText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  list: { marginTop: 20, flex: 1 },
  item: { color: '#adb5bd', fontSize: 13, paddingVertical: 4 },
});
