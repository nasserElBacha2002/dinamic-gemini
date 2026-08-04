import { useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import type { CaptureSnapshot } from '../features/capture/captureService';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, PhotoWorkList, SmallButton, countPhotos, styles } from '../ui';

export interface ReviewScreenProps {
  services: AppServices;
  snapshot: CaptureSnapshot | null;
  onBack: () => void;
  /** Upload now — parent runs completeReview + enqueue. */
  onConfirm: (sessionId: string) => void;
  /** Persist local only (MANUAL) — no upload enqueue. */
  onSaveLocalOnly?: (sessionId: string) => void;
  /** Persist local and enqueue when connectivity returns (WHEN_CONNECTED). */
  onSaveLocalWhenConnected?: (sessionId: string) => void;
  /** @deprecated Prefer onSaveLocalOnly / onSaveLocalWhenConnected */
  onSaveLocal?: (sessionId: string) => void;
  onError: (message: string | null) => void;
}

export function ReviewScreen({
  services,
  snapshot,
  onBack,
  onConfirm,
  onSaveLocalOnly,
  onSaveLocalWhenConnected,
  onSaveLocal,
  onError,
}: ReviewScreenProps) {
  const photos = snapshot?.photos ?? [];
  const counts = countPhotos(photos);
  const canConfirm = counts.waiting === 0 && counts.errors === 0;
  const context = snapshot?.context;
  const flags = services.config.flags;
  const localCompletion = flags.localCompletion !== false;
  const csvExport = flags.mobileCsvExport !== false;
  const [exportBusy, setExportBusy] = useState(false);
  const [exportHint, setExportHint] = useState<string | null>(null);

  const sessionId = snapshot?.session?.id;

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
          {localCompletion ? (
            <Text style={styles.notif}>
              Resultado detectado localmente (CODE_SCAN). El procesamiento remoto puede agregar o
              corregir resultados. La exportación CSV no incluye fotografías.
            </Text>
          ) : null}
          {!canConfirm ? <ErrorText text="Resolvé errores o esperá validaciones antes de confirmar." /> : null}
          {exportHint ? <Text style={styles.row}>{exportHint}</Text> : null}
          {exportBusy ? <ActivityIndicator /> : null}
          <Button
            label="Reintentar errores"
            disabled={counts.errors === 0}
            onPress={() => void services.capture.retryErrors()}
          />
          <Button
            label="Subir imágenes ahora"
            disabled={!canConfirm}
            onPress={() => {
              if (!sessionId) {
                onError('No se encontró la sesión de captura.');
                return;
              }
              onConfirm(sessionId);
            }}
          />
          {localCompletion && (onSaveLocalOnly || onSaveLocal) ? (
            <Button
              label="Guardar solo en el dispositivo"
              disabled={!canConfirm}
              onPress={() => {
                if (!sessionId) {
                  onError('No se encontró la sesión de captura.');
                  return;
                }
                (onSaveLocalOnly ?? onSaveLocal)?.(sessionId);
              }}
            />
          ) : null}
          {localCompletion && (onSaveLocalWhenConnected || onSaveLocal) ? (
            <Button
              label="Guardar y subir cuando haya conexión"
              disabled={!canConfirm}
              onPress={() => {
                if (!sessionId) {
                  onError('No se encontró la sesión de captura.');
                  return;
                }
                (onSaveLocalWhenConnected ?? onSaveLocal)?.(sessionId);
              }}
            />
          ) : null}
          {csvExport ? (
            <Button
              label="Exportar resultados CSV"
              disabled={!canConfirm || exportBusy || !sessionId}
              onPress={() => {
                if (!sessionId || !services.localCsvExport) {
                  onError('Exportación CSV no disponible.');
                  return;
                }
                setExportBusy(true);
                setExportHint(null);
                void services.localCsvExport
                  .exportSession(sessionId)
                  .then(async (exported) => {
                    setExportHint(
                      `CSV listo · ${exported.rowCount} filas · checksum ${exported.checksumSha256.slice(0, 12)}…${
                        exported.reused ? ' (reutilizado)' : ''
                      }`,
                    );
                    await services.localCsvExport!.shareExport(exported.fileUri, exported.exportId);
                  })
                  .catch((e) => onError(e instanceof Error ? e.message : String(e)))
                  .finally(() => setExportBusy(false));
              }}
            />
          ) : null}
          {!localCompletion ? (
            <Button
              label="Confirmar y continuar"
              disabled={!canConfirm}
              onPress={() => {
                if (!sessionId) {
                  onError('No se encontró la sesión de captura.');
                  return;
                }
                onConfirm(sessionId);
              }}
            />
          ) : null}
        </View>
      }
    />
  );
}
