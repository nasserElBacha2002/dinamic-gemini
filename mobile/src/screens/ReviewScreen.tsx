import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import type { LocalDetectionDraftRow } from '../database/repositories/localDetectionDraftRepository';
import type { CaptureSnapshot } from '../features/capture/captureService';
import {
  canExportSession,
  countIncompleteLocalCodeScans,
} from '../features/localCsv/canExportSession';
import {
  mapLocalCsvExportError,
  runLocalCsvExport,
  userMessageForLocalCsvExportError,
} from '../features/localCsv/runLocalCsvExport';
import {
  emptyExportPrepCounts,
  type ExportPrepCounts,
  type ExportPrepDrainResult,
  type ExportPrepSettleResult,
} from '../features/exportPrep/exportPrepQueue';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, PhotoWorkList, SmallButton, countPhotos, messageOf, styles } from '../ui';

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
  const localCodeScanEnabled = services.config.flags.mobileLocalCodeScan === true;
  const prepQueue = services.exportPrepQueue;
  const [exportBusy, setExportBusy] = useState(false);
  const [exportHint, setExportHint] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<LocalDetectionDraftRow[]>([]);
  const [prepCounts, setPrepCounts] = useState<ExportPrepCounts>(emptyExportPrepCounts());
  const [prepExportability, setPrepExportability] = useState<ExportPrepSettleResult | null>(null);
  const [drainBusy, setDrainBusy] = useState(false);
  const [zipProgress, setZipProgress] = useState<string | null>(null);

  const sessionId = snapshot?.session?.id;
  const sessionStatus = snapshot?.session?.status;
  const isLocalCompleted = sessionStatus === 'local_completed';
  const isReadOnly = isLocalCompleted;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const refreshDrafts = useCallback(() => {
    if (!sessionId || !localCodeScanEnabled) {
      setDrafts([]);
      return;
    }
    void services.localDetectionDrafts.listForSession(sessionId).then(setDrafts).catch(() => {
      setDrafts([]);
    });
  }, [localCodeScanEnabled, services, sessionId]);

  useEffect(() => {
    refreshDrafts();
    if (!sessionId || !localCodeScanEnabled) {
      return;
    }
    const t = setInterval(refreshDrafts, 1500);
    return () => clearInterval(t);
  }, [localCodeScanEnabled, refreshDrafts, sessionId]);

  useEffect(() => {
    if (!prepQueue || !sessionId) {
      setPrepCounts(emptyExportPrepCounts());
      setPrepExportability(null);
      return;
    }
    let cancelled = false;
    void prepQueue
      .ensureJobsForEligiblePhotos(sessionId, { reason: 'REVIEW_OPEN' })
      .then(async (ensured) => {
        if (cancelled) return;
        const counts = await prepQueue.getCounts(sessionId);
        const gate = await prepQueue.evaluateExportability(sessionId);
        if (cancelled) return;
        setPrepCounts(counts);
        setPrepExportability(gate);
        if (ensured.partialErrors.length > 0 || ensured.missingSourcePhotos > 0) {
          onErrorRef.current(
            `Backfill de preparación incompleto (fuentes: ${ensured.missingSourcePhotos}, errores: ${ensured.partialErrors.length}).`,
          );
        }
      })
      .catch((e) => {
        if (!cancelled) onErrorRef.current(messageOf(e));
      });
    return () => {
      cancelled = true;
    };
  }, [prepQueue, sessionId]);

  useEffect(() => {
    if (!prepQueue || !sessionId) {
      return;
    }
    return prepQueue.subscribe((sid, c) => {
      if (sid === sessionId || sid == null) {
        setPrepCounts(c);
        void prepQueue.evaluateExportability(sessionId).then(setPrepExportability);
      }
    });
  }, [prepQueue, sessionId]);

  const resumeDrain = useCallback(async () => {
    if (!prepQueue || !sessionId || drainBusy) return;
    setDrainBusy(true);
    try {
      const drain: ExportPrepDrainResult = await prepQueue.waitUntilExportable(sessionId, {
        reason: 'RECOVERY',
        timeoutMs: 5 * 60_000,
        pollMs: 500,
      });
      setPrepCounts(await prepQueue.getCounts(sessionId));
      setPrepExportability(await prepQueue.evaluateExportability(sessionId));
      if (drain.timedOut) {
        onErrorRef.current(
          `Preparación aún en curso (${drain.ready}/${drain.totalEligible}). Reintentá la espera.`,
        );
      }
    } catch (e) {
      onErrorRef.current(messageOf(e));
    } finally {
      setDrainBusy(false);
    }
  }, [drainBusy, prepQueue, sessionId]);

  const incompleteScans = localCodeScanEnabled
    ? countIncompleteLocalCodeScans({ photos, drafts })
    : 0;
  const prepBlocksExport =
    prepQueue != null &&
    (prepExportability != null
      ? !prepExportability.ok
      : prepCounts.pending > 0 ||
        prepCounts.failedRetryable > 0 ||
        prepCounts.failedTerminal > 0);
  const prepBlockCount =
    (prepExportability?.pending ?? prepCounts.pending) +
    (prepExportability?.failedRetryable ?? prepCounts.failedRetryable) +
    (prepExportability?.failedTerminal ?? prepCounts.failedTerminal);
  const freezeId = snapshot?.session?.active_freeze_id;
  const freezeGen = snapshot?.session?.capture_freeze_generation;
  const exportGate = canExportSession({
    session: snapshot?.session,
    photos,
    csvExportEnabled: csvExport,
    exportInProgress: exportBusy,
    localCodeScanEnabled,
    localDetectionDrafts: drafts,
  });
  const exportBlockedByScan = !exportGate.ok && incompleteScans > 0;

  return (
    <PhotoWorkList
      photos={photos}
      readOnly={isReadOnly}
      onExclude={(id) => {
        if (services.exportPrepPhotoCoordinator) {
          void services.exportPrepPhotoCoordinator.excludeByAssetId(id).catch((e) => onError(messageOf(e)));
        } else {
          void services.capture.exclude(id);
        }
      }}
      onReinclude={(id) => {
        if (services.exportPrepPhotoCoordinator) {
          void services.exportPrepPhotoCoordinator
            .reincorporateByAssetId(id)
            .catch((e) => onError(messageOf(e)));
        } else {
          void services.capture.reincorporate(id);
        }
      }}
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
          {prepQueue ? (
            <Text style={styles.row}>
              Prep · elegibles: {prepExportability?.totalEligible ?? '—'} · listas:{' '}
              {prepCounts.ready} · cola: {prepCounts.queued} · proc: {prepCounts.processing} ·
              retry: {prepCounts.failedRetryable} · terminal: {prepCounts.failedTerminal}
              {prepExportability && prepExportability.missingJobs > 0
                ? ` · faltan jobs: ${prepExportability.missingJobs}`
                : ''}
            </Text>
          ) : null}
          {prepQueue && freezeId ? (
            <Text style={styles.muted}>
              Freeze {freezeId.slice(0, 8)}… · gen {freezeGen ?? 0}
              {prepExportability?.ok ? ' · exportable' : ' · no exportable'}
            </Text>
          ) : null}
          {!canConfirm && !isLocalCompleted ? (
            <ErrorText text="Resolvé errores o esperá validaciones antes de continuar." />
          ) : null}
          {exportBlockedByScan ? (
            <Text style={styles.muted}>
              Escaneando códigos locales… ({incompleteScans} pendiente
              {incompleteScans === 1 ? '' : 's'}). El export se habilita al terminar.
            </Text>
          ) : null}
          {prepBlocksExport ? (
            <Text style={styles.muted}>
              {prepCounts.failedTerminal > 0
                ? `Hay ${prepCounts.failedTerminal} fallo(s) terminal(es). Reintentá o excluí antes de exportar.`
                : 'Preparación de exportación incompleta. Reintentá fallidas o esperá el drenaje.'}
            </Text>
          ) : null}
          {exportHint ? <Text style={styles.row}>{exportHint}</Text> : null}
          {zipProgress ? <Text style={styles.row}>{zipProgress}</Text> : null}
          {exportBusy ? <ActivityIndicator /> : null}
          {!isReadOnly ? (
            <Button
              label="Reintentar errores"
              disabled={counts.errors === 0}
              onPress={() => void services.capture.retryErrors()}
            />
          ) : null}
          {prepQueue && prepCounts.failed > 0 && sessionId ? (
            <Button
              label={`Reintentar prep fallidas (${prepCounts.failed})`}
              disabled={drainBusy}
              onPress={() => {
                void prepQueue.retryFailedForSession(sessionId).then(() => resumeDrain());
              }}
            />
          ) : null}
          {prepQueue && sessionId && prepBlocksExport ? (
            <Button
              label={drainBusy ? 'Esperando preparación…' : 'Reanudar preparación'}
              disabled={drainBusy}
              onPress={() => void resumeDrain()}
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
              label={
                exportBusy
                  ? 'Exportando ZIP…'
                  : prepBlocksExport
                    ? prepCounts.failedTerminal > 0
                      ? `Prep bloqueada (${prepCounts.failedTerminal} terminal)`
                      : `Prep pendiente (${prepBlockCount})`
                    : exportBlockedByScan
                      ? `Escaneando… (${incompleteScans})`
                      : 'Exportar ZIP (CSV + fotos)'
              }
              disabled={
                exportBusy ||
                !exportGate.ok ||
                prepBlocksExport ||
                !sessionId ||
                !services.localCsvExport
              }
              onPress={() => {
                if (!sessionId || !services.localCsvExport) {
                  onError('Exportación no disponible.');
                  return;
                }
                if (!exportGate.ok) {
                  onError(exportGate.reason);
                  return;
                }
                if (prepBlocksExport) {
                  onError(
                    prepCounts.failedTerminal > 0
                      ? 'Hay fallos terminales de preparación. Reintentá o excluí.'
                      : 'Hay fotos sin preparar o con error de preparación.',
                  );
                  return;
                }
                setExportBusy(true);
                setExportHint(null);
                setZipProgress('Preparando ZIP…');
                if (services.localCsvExport) {
                  services.localCsvExport.setZipProgressListener((done, total) => {
                    setZipProgress(`ZIP ${done}/${total}`);
                  });
                }
                // Authoritative preflight lives in LocalCsvExportService.ensureExportPrepJobs.
                void runLocalCsvExport(services.localCsvExport!, sessionId)
                  .then(({ exported }) => {
                    setZipProgress(null);
                    setExportHint(
                      `Listo · ${exported.rowCount} filas · ${exported.photoCount} fotos · ${
                        exported.zipUri ? 'ZIP' : 'CSV'
                      } ${exported.checksumSha256.slice(0, 12)}…${
                        exported.reused ? ' (reutilizado)' : ''
                      }${
                        exported.scanMode === 'skipped_all_ready'
                          ? ' · sin reescaneo'
                          : ''
                      }`,
                    );
                  })
                  .catch((e) => {
                    onError(userMessageForLocalCsvExportError(mapLocalCsvExportError(e)));
                  })
                  .finally(() => {
                    services.localCsvExport?.setZipProgressListener(null);
                    setExportBusy(false);
                    setZipProgress(null);
                  });
              }}
            />
          ) : null}
        </View>
      }
    />
  );
}
