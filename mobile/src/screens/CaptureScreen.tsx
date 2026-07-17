import { useEffect, useState } from 'react';
import { Alert, AppState, Text, View } from 'react-native';

import { OtherAisleCaptureActiveError, type CaptureSnapshot } from '../features/capture/captureService';
import { userMessageForCode } from '../core/errorCatalog';
import { getPhotoPermission, requestPhotoPermission } from '../native/mediaStore';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import type { AisleDto, InventoryListItemDto } from '../services/api/types';
import { Button, ErrorText, PhotoWorkList, SmallButton, captureContextFrom, countPhotos, messageOf, styles } from '../ui';

export interface CaptureScreenProps {
  services: AppServices;
  inventory: InventoryListItemDto | null;
  aisle: AisleDto | null;
  snapshot: CaptureSnapshot | null;
  onReview: () => void;
  onBackToAisles: () => void;
  onError: (message: string | null) => void;
}

export function CaptureScreen({
  services,
  inventory,
  aisle,
  snapshot,
  onReview,
  onBackToAisles,
  onError,
}: CaptureScreenProps) {
  const [permission, setPermission] = useState('desconocido');
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
    await services.capture.start(
      {
        inventoryId: inventory.id,
        inventoryName: inventory.name,
        aisleId: aisle.id,
        aisleName: aisle.code,
        permission: p,
      },
      { pauseOtherAisle },
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
          <Text style={styles.row}>Estado: {sessionStatus ?? 'sin iniciar'}</Text>
          <Text style={styles.row}>
            FGS activo: {snapshotBelongsToSelectedAisle && snapshot?.fgsActive ? 'sí' : 'no'}
          </Text>
          <Text style={styles.row}>
            Detectadas: {counts.total} · Validando: {counts.waiting} · Estables: {counts.stable} · Error:{' '}
            {counts.errors} · Excluidas: {counts.excluded}
          </Text>
          <Button
            label={sessionStatus === 'paused' ? 'Continuar captura' : 'Comenzar captura'}
            disabled={!inventory || !aisle || Boolean(snapshotBelongsToSelectedAisle && sessionStatus === 'active')}
            onPress={() => {
              if (snapshotBelongsToSelectedAisle && sessionStatus === 'paused') {
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
              disabled={sessionStatus !== 'active'}
              onPress={() => void services.capture.requestScan()}
            />
            <SmallButton
              label="Pausar"
              disabled={sessionStatus !== 'active'}
              onPress={() => void services.capture.pause()}
            />
            <SmallButton
              label="Reanudar"
              disabled={sessionStatus !== 'paused'}
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
            disabled={sessionStatus !== 'active' && sessionStatus !== 'paused'}
            onPress={() => void services.capture.finish().then(onReview).catch((e) => onError(messageOf(e)))}
          />
        </View>
      }
    />
  );
}
