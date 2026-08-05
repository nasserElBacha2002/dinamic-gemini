import { useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import type { CaptureSnapshot } from '../features/capture/captureService';
import { canExportSession } from '../features/localCsv/canExportSession';
import {
  mapLocalCsvExportError,
  runLocalCsvExport,
  userMessageForLocalCsvExportError,
} from '../features/localCsv/runLocalCsvExport';
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
  /** Optional: open uploads for a locally completed session. */
  onOpenUploads?: (sessionId: string) => void;
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
  onOpenUploads,
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
  const sessionStatus = snapshot?.session?.status;
  const isLocalCompleted = sessionStatus === 'local_completed';
  const isReadOnly = isLocalCompleted;
  const exportGate = canExportSession({
    session: snapshot?.session,
    photos,
    csvExportEnabled: csvExport,
    exportInProgress: exportBusy,
  });

  return (
    <PhotoWorkList
      photos={photos}
      readOnly={isReadOnly}
      onExclude={(id) => void services.capture.exclude(id)}
      onReinclude={(id) => void services.capture.reincorporate(id)}
      header={
        <View>
          <SmallButton
            label={isLocalCompleted ? '← Actividad' : '← Captura'}
            onPress={onBack}
          />
          <Text style={styles.h2}>
            {isLocalCompleted ? 'Captura guardada' : 'Revisión'} ·{' '}
            {context?.inventoryName ?? 'Inventario'} / {context?.aisleName ?? 'Pasillo'}
          </Text>
          {isLocalCompleted ? (
            <Text style={styles.notif}>
              Guardada solo en el dispositivo. Podés exportar el ZIP o subir cuando corresponda.
            </Text>
          ) : null}
          <Text style={styles.row}>
            Estables: {counts.stable} · Excluidas: {counts.excluded} · Errores: {counts.errors}
          </Text>
          {localCompletion && !isLocalCompleted ? (
            <Text style={styles.notif}>
              Resultado detectado localmente (CODE_SCAN). La exportación genera un ZIP con
              el CSV y las fotos del freeze para importar luego en el sistema.
            </Text>
          ) : null}
          {!canConfirm && !isLocalCompleted ? (
            <ErrorText text="Resolvé errores o esperá validaciones antes de confirmar." />
          ) : null}
          {exportHint ? <Text style={styles.row}>{exportHint}</Text> : null}
          {exportBusy ? <ActivityIndicator /> : null}
          {!isReadOnly ? (
            <Button
              label="Reintentar errores"
              disabled={counts.errors === 0}
              onPress={() => void services.capture.retryErrors()}
            />
          ) : null}
          {!isLocalCompleted ? (
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
          ) : onOpenUploads && sessionId ? (
            <Button label="Ir a cargas" onPress={() => onOpenUploads(sessionId)} />
          ) : null}
          {!isLocalCompleted && localCompletion && (onSaveLocalOnly || onSaveLocal) ? (
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
          {!isLocalCompleted && localCompletion && (onSaveLocalWhenConnected || onSaveLocal) ? (
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
              label="Exportar ZIP (CSV + fotos)"
              disabled={!exportGate.ok || !sessionId || !services.localCsvExport}
              onPress={() => {
                if (!sessionId || !services.localCsvExport) {
                  onError('Exportación no disponible.');
                  return;
                }
                if (!exportGate.ok) {
                  onError(exportGate.reason);
                  return;
                }
                setExportBusy(true);
                setExportHint(null);
                void runLocalCsvExport(services.localCsvExport, sessionId)
                  .then(({ exported }) => {
                    setExportHint(
                      `Listo · ${exported.rowCount} filas · ${exported.photoCount} fotos · ${
                        exported.zipUri ? 'ZIP' : 'CSV'
                      } ${exported.checksumSha256.slice(0, 12)}…${
                        exported.reused ? ' (reutilizado)' : ''
                      }`,
                    );
                  })
                  .catch((e) => {
                    onError(userMessageForLocalCsvExportError(mapLocalCsvExportError(e)));
                  })
                  .finally(() => setExportBusy(false));
              }}
            />
          ) : null}
          {!localCompletion && !isLocalCompleted ? (
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
