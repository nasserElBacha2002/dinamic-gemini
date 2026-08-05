import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Text, View } from 'react-native';

import { OtherAisleCaptureActiveError, type CaptureSnapshot } from '../features/capture/captureService';
import { userMessageForCode } from '../core/errorCatalog';
import { getPhotoPermission, requestPhotoPermission } from '../native/mediaStore';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, PhotoWorkList, SmallButton, captureContextFrom, countPhotos, messageOf, styles } from '../ui';
import { FINISH_STAGE_LABELS } from '../features/capture/finishObservability';

export interface CaptureScreenProps {
  services: AppServices;
  inventory: InventoryListItemDto | null;
  aisle: AisleDto | null;
  snapshot: CaptureSnapshot | null;
  onReview: () => void;
  onBackToAisles: () => void;
  onError: (message: string | null) => void;
  /**
   * When true, "Comenzar captura" always creates a new session (forceNew).
   * When false, start() may resume paused/review work on the same aisle.
   */
  forceNewCapture?: boolean;
}

export function CaptureScreen({
  services,
  inventory,
  aisle,
  snapshot,
  onReview,
  onBackToAisles,
  onError,
  forceNewCapture = false,
}: CaptureScreenProps) {
  const [permission, setPermission] = useState('desconocido');
  const [finishInFlight, setFinishInFlight] = useState(false);
  const snapshotBelongsToSelectedAisle = Boolean(
    snapshot?.session &&
      inventory &&
      aisle &&
      snapshot.context?.inventoryId === inventory.id &&
      snapshot.context?.aisleId === aisle.id,
  );
  const context = captureContextFrom(snapshotBelongsToSelectedAisle ? snapshot : null, inventory, aisle);

  const runStart = async (pauseOtherAisle: boolean) => {
    if (!inventory || !aisle) {
      throw new Error('Seleccioná inventario y pasillo para iniciar una captura nueva.');
    }
    const storage = await services.getStorageStatus();
    if (storage.lowSpace) {
      throw new Error(userMessageForCode('CAPTURE_STORAGE_LOW'));
    }
    const p = await requestPhotoPermission();
    setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
    const startOpts = { pauseOtherAisle, forceNew: forceNewCapture };
    if (forceNewCapture) {
      await services.capture.startNewSession(
        {
          inventoryId: inventory.id,
          inventoryName: inventory.name,
          aisleId: aisle.id,
          aisleName: aisle.code,
          permission: p,
        },
        { pauseOtherAisle },
      );
      return;
    }
    await services.capture.start(
      {
        inventoryId: inventory.id,
        inventoryName: inventory.name,
        aisleId: aisle.id,
        aisleName: aisle.code,
        permission: p,
      },
      startOpts,
    );
  };

  const start = async () => {
    try {
      await runStart(false);
    } catch (e) {
      if (e instanceof OtherAisleCaptureActiveError) {
        Alert.alert(
          'Captura en otro pasillo',
          `Hay otra captura activa en el pasillo ${e.otherSession.aisle_name}.\n\n¿Querés pausarla y comenzar una captura en este pasillo?`,
          [
            { text: 'Cancelar', style: 'cancel' },
            {
              text: 'Pausar y continuar',
              onPress: () => void runStart(true).catch((err) => onError(messageOf(err))),
            },
          ],
        );
        return;
      }
      throw e;
    }
  };

  useEffect(() => {
    void getPhotoPermission().then((p) =>
      setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado'),
    );
  }, []);

  const photos = snapshotBelongsToSelectedAisle ? snapshot?.photos ?? [] : [];
  const counts = countPhotos(photos);
  const sessionStatus = snapshotBelongsToSelectedAisle ? snapshot?.session?.status : undefined;
  const isFinishing = finishInFlight || sessionStatus === 'finishing';
  const finishStageLabel =
    snapshotBelongsToSelectedAisle && snapshot?.finishStage
      ? FINISH_STAGE_LABELS[snapshot.finishStage]
      : null;

  useEffect(() => {
    if (sessionStatus !== 'active') return;
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        void services.capture.requestScan();
      }
    });
    return () => sub.remove();
  }, [sessionStatus, services.capture]);

  return (
    <PhotoWorkList
      photos={photos}
      onExclude={(id) => void services.capture.exclude(id)}
      onReinclude={(id) => void services.capture.reincorporate(id)}
      header={
        <View>
          <SmallButton label="← Pasillos" onPress={onBackToAisles} />
          <Text style={styles.h2}>
            Captura · {context?.inventoryName ?? inventory?.name ?? 'Inventario'} /{' '}
            {context?.aisleName ?? aisle?.code ?? 'Pasillo'}
          </Text>
          {snapshotBelongsToSelectedAisle && snapshot?.warning ? <ErrorText text={snapshot.warning} /> : null}
          <Text style={styles.row}>Permiso fotos: {permission}</Text>
          <Text style={styles.row}>Estado: {isFinishing ? 'finalizando…' : sessionStatus ?? 'sin iniciar'}</Text>
          <Text style={styles.row}>
            FGS activo: {snapshotBelongsToSelectedAisle && snapshot?.fgsActive ? 'sí' : 'no'}
          </Text>
          <Text style={styles.row}>
            Detectadas: {counts.total} · Validando: {counts.waiting} · Estables: {counts.stable} · Error:{' '}
            {counts.errors} · Excluidas: {counts.excluded}
          </Text>
          {isFinishing ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginVertical: 8 }}>
              <ActivityIndicator />
              <Text style={styles.row}>
                {finishStageLabel ?? 'Cerrando captura y preparando revisión…'}
              </Text>
            </View>
          ) : null}
          <Button
            label={
              sessionStatus === 'paused' && !forceNewCapture
                ? 'Continuar captura'
                : forceNewCapture
                  ? 'Comenzar nueva captura'
                  : 'Comenzar captura'
            }
            disabled={
              isFinishing ||
              !inventory ||
              !aisle ||
              Boolean(snapshotBelongsToSelectedAisle && sessionStatus === 'active' && !forceNewCapture)
            }
            onPress={() => {
              if (snapshotBelongsToSelectedAisle && sessionStatus === 'paused' && !forceNewCapture) {
                void requestPhotoPermission()
                  .then((p) => {
                    setPermission(p.granted ? (p.limited ? 'parcial' : 'completo') : 'denegado');
                    return services.capture.resume(p);
                  })
                  .catch((e) => onError(messageOf(e)));
                return;
              }
              void start().catch((e) => onError(messageOf(e)));
            }}
          />
          <View style={styles.nav}>
            <SmallButton
              label="Escanear"
              disabled={isFinishing || sessionStatus !== 'active'}
              onPress={() => void services.capture.requestScan()}
            />
            <SmallButton
              label="Pausar"
              disabled={isFinishing || sessionStatus !== 'active'}
              onPress={() => void services.capture.pause()}
            />
            <SmallButton
              label="Reanudar"
              disabled={isFinishing || sessionStatus !== 'paused'}
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
            label={isFinishing ? 'Finalizando…' : 'Finalizar captura'}
            disabled={
              isFinishing || (sessionStatus !== 'active' && sessionStatus !== 'paused')
            }
            onPress={() => {
              setFinishInFlight(true);
              onError(null);
              void (async () => {
                const sessionId = snapshot?.session?.id;
                if (sessionId) {
                  // Re-read DB: process start / uploads may have moved status while UI still showed active.
                  const fresh = await services.capture.getSessionSnapshot(sessionId);
                  const status = fresh.session?.status;
                  if (
                    status &&
                    status !== 'active' &&
                    status !== 'paused' &&
                    status !== 'finishing' &&
                    status !== 'processing'
                  ) {
                    throw new Error(`No se puede finalizar la captura desde el estado "${status}".`);
                  }
                }
                await services.capture.finish();
                onReview();
              })().catch((e) => {
                setFinishInFlight(false);
                onError(messageOf(e));
              });
            }}
          />
        </View>
      }
    />
  );
}
