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
  /**
   * Upload photos + local results to the server (no AI reprocess).
   * Parent runs confirm drafts (if needed) + completeReview + enqueue.
   */
  onConfirm: (sessionId: string) => void;
  /** @deprecated Prefer onConfirm / ZIP export — kept for tests / legacy wiring */
  onSaveLocalOnly?: (sessionId: string) => void;
  /** @deprecated Prefer onConfirm / ZIP export */
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

  const twoWayHandoff = localCompletion;

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
          {twoWayHandoff && !isLocalCompleted ? (
            <Text style={styles.notif}>
              Elegí una opción: subir fotos y resultados locales al servidor (sin reprocesar con
              IA), o exportar un ZIP para importar después.
            </Text>
          ) : null}
          {isLocalCompleted ? (
            <Text style={styles.notif}>
              Guardada en el dispositivo. Podés exportar el ZIP o continuar la carga al servidor.
            </Text>
          ) : null}
          <Text style={styles.row}>
            Estables: {counts.stable} · Excluidas: {counts.excluded} · Errores: {counts.errors}
          </Text>
          {!canConfirm && !isLocalCompleted ? (
            <ErrorText text="Resolvé errores o esperá validaciones antes de continuar." />
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
              label={
                twoWayHandoff ? 'Subir fotos y resultados' : 'Confirmar y continuar'
              }
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
            <Button label="Continuar carga al servidor" onPress={() => onOpenUploads(sessionId)} />
          ) : null}
          {csvExport ? (
            <Button
              label={exportBusy ? 'Exportando ZIP…' : 'Exportar ZIP (CSV + fotos)'}
              disabled={exportBusy || !sessionId || !services.localCsvExport}
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
        </View>
      }
    />
  );
}
