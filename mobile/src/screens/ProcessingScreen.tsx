import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { ProcessAisleConfirmModal } from '../components/ProcessAisleConfirmModal';
import {
  primaryProcessingAction,
  primaryProcessingActionLabel,
  processingStateLabel,
  processingStateLabelFromRemote,
  type ProcessingState,
} from '../core/processingState';
import type { ConfirmedLocalResultRow } from '../database/repositories/confirmedLocalResultRepository';
import {
  countExcludedPhotos,
  countPendingLocalResults,
} from '../features/processing/aisleProcessDialogHelpers';
import type { AisleIdentificationMode, IdentificationModeSelection } from '../features/processing/processingMode';
import {
  labelForIdentificationMode,
  preferenceFromSelection,
} from '../features/processing/processingMode';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, SmallButton, messageOf, styles } from '../ui';
import {
  reconciliationOutcomeLabel,
  type ReconciliationSummary,
} from '../features/preliminaryReconciliation/reconciliationQueryService';

export interface ProcessingScreenProps {
  services: AppServices;
  sessionId: string;
  inventoryName?: string;
  aisleName?: string;
  identificationModePreference: AisleIdentificationMode | null;
  onIdentificationModePreferenceChange: (next: AisleIdentificationMode | null) => void;
  onBack: () => void;
  onAnotherAisle: () => void;
  onViewResults: () => void;
  onViewAisleResults?: () => void;
  onExcludedPhotos?: () => void;
  onError: (message: string | null) => void;
}

export function ProcessingScreen({
  services,
  sessionId,
  inventoryName = '',
  aisleName = '',
  identificationModePreference,
  onIdentificationModePreferenceChange,
  onBack,
  onAnotherAisle,
  onViewResults,
  onViewAisleResults,
  onExcludedPhotos,
  onError,
}: ProcessingScreenProps) {
  const [view, setView] = useState<Awaited<ReturnType<AppServices['processing']['getSessionProcessingView']>> | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [reconciliationSummary, setReconciliationSummary] = useState<ReconciliationSummary | null>(
    null,
  );
  const [localResults, setLocalResults] = useState<ConfirmedLocalResultRow[]>([]);
  const [excludedPhotoCount, setExcludedPhotoCount] = useState(0);
  const [uploadLocalBusy, setUploadLocalBusy] = useState(false);
  const [uploadLocalMessage, setUploadLocalMessage] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void services.processing.getSessionProcessingView(sessionId).then(setView);
    void services.confirmedLocalResults.listForSession(sessionId).then(setLocalResults);
    void services.capture.loadSession(sessionId, false).then((snap) => {
      setExcludedPhotoCount(countExcludedPhotos(snap.photos ?? []));
    });
  }, [services, sessionId]);

  useEffect(() => {
    refresh();
    const unsub = services.jobMonitor.subscribe(() => refresh());
    const t = setInterval(refresh, 4000);
    return () => {
      unsub();
      clearInterval(t);
    };
  }, [refresh, services]);

  useEffect(() => {
    if (view?.jobId && view.state !== 'completed' && view.state !== 'failed' && view.state !== 'cancelled') {
      void services.jobMonitor.watch(view.jobId);
    }
  }, [services, view?.jobId, view?.state]);

  useEffect(() => {
    if (!services.reconciliation.isViewEnabled() || !view?.inventoryId || !view?.aisleId) {
      setReconciliationSummary(null);
      return;
    }
    if (view.state !== 'completed' && view.state !== 'failed') {
      return;
    }
    void services.reconciliation
      .fetchForAisle(view.inventoryId, view.aisleId, view.jobId ?? undefined)
      .then(setReconciliationSummary)
      .catch(() => setReconciliationSummary(null));
  }, [services, view?.inventoryId, view?.aisleId, view?.state, view?.jobId]);

  const state: ProcessingState = view?.state ?? 'idle';
  const action = primaryProcessingAction(state);

  const startOrResumeProcessing = async (selection: IdentificationModeSelection) => {
    if (busy) return;
    setBusy(true);
    setConfirmError(null);
    const modeAtConfirm = preferenceFromSelection(selection);
    onIdentificationModePreferenceChange(modeAtConfirm);
    try {
      const res = await services.processing.startProcess(sessionId, {
        identificationMode: modeAtConfirm,
      });
      if (!res.ok) {
        setConfirmError(res.reason);
        onError(res.reason);
        return;
      }
      setConfirmVisible(false);
      if (res.jobId) await services.jobMonitor.watch(res.jobId);
      refresh();
    } catch (e) {
      const msg = messageOf(e);
      setConfirmError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  const uploadLocalResults = (resultId?: string | null) => {
    if (uploadLocalBusy) return;
    setUploadLocalBusy(true);
    setUploadLocalMessage(null);
    setConfirmError(null);
    const selected = (resultId ?? '').trim();
    const syncPromise = selected
      ? services.authoritativeLocalSync.syncResults([selected])
      : services.authoritativeLocalSync.syncPendingForSession(sessionId);
    void syncPromise
      .then((summary) => {
        if (summary.synced > 0) {
          setUploadLocalMessage(
            selected
              ? 'Resultado local subido correctamente'
              : `Resultados del pasillo: ${summary.synced} subido(s)`,
          );
        } else if (summary.retry > 0) {
          setUploadLocalMessage('La subida quedó pendiente y se reintentará');
        } else if (summary.conflict > 0) {
          setUploadLocalMessage(
            'El servidor ya tiene una versión diferente de este resultado',
          );
        } else if (summary.attempted === 0) {
          setUploadLocalMessage('No hay resultados pendientes de este pasillo para subir');
        } else {
          setUploadLocalMessage(
            `Subida pasillo: ${summary.synced} ok · ${summary.retry} reintento · ${summary.conflict} conflicto`,
          );
        }
        refresh();
      })
      .catch((e) => {
        const msg = messageOf(e);
        setConfirmError(msg);
        onError(msg);
      })
      .finally(() => setUploadLocalBusy(false));
  };

  return (
    <View>
      <SmallButton label="← Pasillos" onPress={onBack} />
      <Text style={styles.h2}>Procesamiento</Text>
      <Text style={styles.row}>Estado local: {processingStateLabel(view?.localState ?? 'idle')}</Text>
      <Text style={styles.row}>Estado remoto: {processingStateLabel(state)}</Text>
      <Text style={styles.muted}>
        Preferencia de tipo: {labelForIdentificationMode(identificationModePreference)}
      </Text>
      {view?.remoteStatus ? (
        <Text style={styles.muted}>Detalle remoto: {processingStateLabelFromRemote(view.remoteStatus)}</Text>
      ) : null}
      {view?.updatedAt ? <Text style={styles.muted}>Última actualización: {view.updatedAt}</Text> : null}
      {view?.errorMessage && (state === 'failed' || state === 'unknown') ? (
        <ErrorText text={view.errorMessage} />
      ) : null}
      {action === 'view_result' ? (
        <Button label="Ver resultado" onPress={onViewResults} />
      ) : (
        <Button
          label={busy ? 'Iniciando…' : primaryProcessingActionLabel(state)}
          disabled={busy || action === 'busy'}
          onPress={() => {
            if (action === 'refresh') {
              refresh();
              if (view?.jobId) void services.jobMonitor.refresh(view.jobId);
              return;
            }
            setConfirmError(null);
            setConfirmVisible(true);
          }}
        />
      )}
      {view?.jobId ? <Text style={styles.muted}>Diagnóstico job: {view.jobId}</Text> : null}
      {reconciliationSummary ? (
        <View>
          <Text style={styles.row}>Comparación local vs servidor (diagnóstico)</Text>
          <Text style={styles.muted}>
            Comparable: {reconciliationSummary.comparable} · No comparable:{' '}
            {reconciliationSummary.notComparable}
            {reconciliationSummary.serverAgreementRate != null
              ? ` · Acuerdo con servidor: ${(reconciliationSummary.serverAgreementRate * 100).toFixed(0)}%`
              : ''}
          </Text>
          {Object.entries(reconciliationSummary.byOutcome)
            .slice(0, 6)
            .map(([outcome, count]) => (
              <Text key={outcome} style={styles.muted}>
                {reconciliationOutcomeLabel(outcome)}: {count}
              </Text>
            ))}
          <Text style={styles.muted}>{reconciliationSummary.authorityNotice}</Text>
        </View>
      ) : null}
      <Button label="Capturar otro pasillo" onPress={onAnotherAisle} />
      <Text style={styles.muted}>
        Podés capturar otro pasillo mientras este se procesa. No se mezclan fotos ni lotes.
      </Text>
      <ProcessAisleConfirmModal
        visible={confirmVisible}
        inventoryName={inventoryName}
        aisleName={aisleName}
        uploadedCount={0}
        pendingCount={0}
        pendingLocalResultCount={countPendingLocalResults(localResults)}
        excludedPhotoCount={excludedPhotoCount}
        localResults={localResults}
        preference={identificationModePreference}
        busy={busy}
        error={confirmError}
        uploadLocalBusy={uploadLocalBusy}
        uploadLocalMessage={uploadLocalMessage}
        allowUploadLocalResults={Boolean(
          services.config.flags.mobileAuthoritativeLocalCodeScan,
        )}
        onClose={() => {
          if (busy || uploadLocalBusy) return;
          setConfirmVisible(false);
          setConfirmError(null);
          setUploadLocalMessage(null);
        }}
        onConfirm={(selection) => {
          void startOrResumeProcessing(selection);
        }}
        onUploadLocalResults={uploadLocalResults}
        onViewResults={() => {
          setConfirmVisible(false);
          if (onViewAisleResults) onViewAisleResults();
          else onViewResults();
        }}
        onExcludedPhotos={() => {
          setConfirmVisible(false);
          onExcludedPhotos?.();
        }}
      />
    </View>
  );
}
