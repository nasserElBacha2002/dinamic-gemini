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
  /** Confirms drafts (if needed) and closes the session locally for ZIP export. */
  onConfirm: (sessionId: string) => void;
  onError: (message: string | null) => void;
}

export function ReviewScreen({
  services,
  snapshot,
  onBack,
  onConfirm,
  onError,
}: ReviewScreenProps) {
  const photos = snapshot?.photos ?? [];
  const counts = countPhotos(photos);
  const canConfirm = counts.waiting === 0 && counts.errors === 0;
  const context = snapshot?.context;
  const csvExport = services.config.flags.mobileCsvExport !== false;
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
          {!isLocalCompleted ? (
            <Text style={styles.notif}>
              Revisá las fotos, guardá la captura en el dispositivo y exportá un ZIP (CSV + fotos)
              para importar después.
            </Text>
          ) : null}
          {isLocalCompleted ? (
            <Text style={styles.notif}>
              Guardada en el dispositivo. Exportá el ZIP cuando quieras compartir o importar los
              resultados.
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
              label="Guardar captura"
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
