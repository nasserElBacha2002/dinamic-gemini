import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import {
  primaryProcessingAction,
  primaryProcessingActionLabel,
  processingStateLabel,
  processingStateLabelFromRemote,
  type ProcessingState,
} from '../core/processingState';
import type { AppServices } from '../runtime/bootstrap/createAppServices';
import { Button, ErrorText, SmallButton, messageOf, styles } from '../ui';

export interface ProcessingScreenProps {
  services: AppServices;
  sessionId: string;
  onBack: () => void;
  onAnotherAisle: () => void;
  onViewResults: () => void;
  onError: (message: string | null) => void;
}

export function ProcessingScreen({
  services,
  sessionId,
  onBack,
  onAnotherAisle,
  onViewResults,
  onError,
}: ProcessingScreenProps) {
  const [view, setView] = useState<Awaited<ReturnType<AppServices['processing']['getSessionProcessingView']>> | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    void services.processing.getSessionProcessingView(sessionId).then(setView);
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

  const state: ProcessingState = view?.state ?? 'idle';
  const action = primaryProcessingAction(state);

  const startOrResumeProcessing = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await services.processing.startProcess(sessionId);
      if (!res.ok) {
        onError(res.reason);
        return;
      }
      if (res.jobId) await services.jobMonitor.watch(res.jobId);
      refresh();
    } catch (e) {
      onError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View>
      <SmallButton label="← Pasillos" onPress={onBack} />
      <Text style={styles.h2}>Procesamiento</Text>
      <Text style={styles.row}>Estado local: {processingStateLabel(view?.localState ?? 'idle')}</Text>
      <Text style={styles.row}>Estado remoto: {processingStateLabel(state)}</Text>
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
            void startOrResumeProcessing();
          }}
        />
      )}
      {view?.jobId ? <Text style={styles.muted}>Diagnóstico job: {view.jobId}</Text> : null}
      <Button label="Capturar otro pasillo" onPress={onAnotherAisle} />
      <Text style={styles.muted}>
        Podés capturar otro pasillo mientras este se procesa. No se mezclan fotos ni lotes.
      </Text>
    </View>
  );
}
