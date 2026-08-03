/**
 * Minimal Phase 7 operational positioning panel for mobile.
 * Actions are driven solely by backend allowed_actions.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';

import type { AppServices } from '../../runtime/bootstrap/createAppServices';
import { Button, ErrorText, SmallButton, messageOf, styles } from '../../ui';
import {
  PositioningOperationalApi,
  type AisleOperationalPositioningViewDto,
  type PositioningSequenceDto,
} from './positioningOperationalApi';

function newKey(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface PositioningOperationalPanelProps {
  services: AppServices;
  inventoryId: string;
  aisleId: string;
  onError: (message: string | null) => void;
}

export function PositioningOperationalPanel({
  services,
  inventoryId,
  aisleId,
  onError,
}: PositioningOperationalPanelProps) {
  const apiRef = useRef(new PositioningOperationalApi(services.api));
  const [view, setView] = useState<AisleOperationalPositioningViewDto | null>(null);
  const [sequence, setSequence] = useState<PositioningSequenceDto | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idempotencyRef = useRef(newKey('pos-reprocess'));
  const mounted = useRef(true);
  const processingState = view?.processing_state;

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await apiRef.current.getOperationalView(inventoryId, aisleId);
      if (!mounted.current) return;
      setView(next);
      if (next.result_job_id && next.feature_flags.POSITION_OPERATIONAL_UX_ENABLED !== false) {
        const seq = await apiRef.current.getSequence(inventoryId, aisleId, next.result_job_id, 1, 20);
        if (mounted.current) setSequence(seq);
      } else if (mounted.current) {
        setSequence(null);
      }
    } catch (e) {
      const msg = messageOf(e);
      if (mounted.current) {
        setError(msg);
        onError(msg);
      }
    }
  }, [inventoryId, aisleId, onError]);

  useEffect(() => {
    mounted.current = true;
    void load();
    const active = new Set([
      'PREPARING',
      'UPLOADING',
      'STARTING',
      'RUNNING',
      'FINALIZING',
      'SUSPECTED_STALE',
      'RECOVERY_REQUIRED',
    ]);
    const timer = setInterval(() => {
      if (processingState && active.has(processingState)) void load();
    }, 4000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [load, processingState]);

  if (view?.feature_flags.POSITION_OPERATIONAL_UX_ENABLED === false) {
    return null;
  }

  const onRecover = async () => {
    if (!view?.allowed_actions.recover || busy) return;
    setBusy(true);
    try {
      await services.processing.recoverAisleProcessing(inventoryId, aisleId, {
        reason: 'mobile_positioning_operational_panel',
      });
      await load();
    } catch (e) {
      const msg = messageOf(e);
      setError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  const onReprocess = async (mode: string) => {
    if (!view || busy) return;
    if (mode === 'RECONCILE_ONLY' && !view.allowed_actions.reconcile_only) return;
    if (mode === 'REPROCESS_FULL_AISLE' && !view.allowed_actions.reprocess) return;
    setBusy(true);
    try {
      await apiRef.current.reprocess(inventoryId, aisleId, {
        idempotency_key: idempotencyRef.current,
        reprocess_mode: mode,
        expected_active_job_id: view.active_job_id,
        expected_result_job_id: view.result_job_id,
      });
      idempotencyRef.current = newKey('pos-reprocess');
      await load();
    } catch (e) {
      const msg = messageOf(e);
      setError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ marginTop: 12 }}>
      <Text style={styles.h2}>Posicionamiento operativo</Text>
      {error ? <ErrorText text={error} /> : null}
      {view ? (
        <>
          <Text style={styles.row}>Estado: {view.processing_state}</Text>
          <Text style={styles.muted}>
            Job activo: {view.active_job_id ?? '—'} · Resultados: {view.result_job_id ?? '—'}
          </Text>
          <Text style={styles.muted}>
            Productos {view.total_results} · Con posición {view.assigned_results} · Sin{' '}
            {view.unassigned_results} · Manuales {view.manual_overrides_count}
          </Text>
          {view.warnings.slice(0, 5).map((w) => (
            <Text key={w.code} style={styles.muted}>
              [{w.severity}] {w.title}: {w.description}
            </Text>
          ))}
          {view.allowed_actions.recover ? (
            <Button label={busy ? 'Recuperando…' : 'Recuperar'} disabled={busy} onPress={() => void onRecover()} />
          ) : null}
          {view.allowed_actions.reconcile_only ? (
            <Button
              label={busy ? 'Reconciliando…' : 'Solo reconciliar'}
              disabled={busy}
              onPress={() => void onReprocess('RECONCILE_ONLY')}
            />
          ) : null}
          {view.allowed_actions.reprocess ? (
            <Button
              label={busy ? 'Reprocesando…' : 'Reprocesar pasillo'}
              disabled={busy}
              onPress={() => void onReprocess('REPROCESS_FULL_AISLE')}
            />
          ) : null}
          <SmallButton label="Actualizar estado" onPress={() => void load()} />
          {sequence && sequence.items.length > 0 ? (
            <View style={{ marginTop: 8 }}>
              <Text style={styles.row}>
                Secuencia ({sequence.items.length} de {sequence.total})
              </Text>
              {sequence.items.slice(0, 10).map((frame) => (
                <Text key={frame.source_asset_id} style={styles.muted}>
                  {frame.sequence_number ?? '—'} · {frame.filename || frame.source_asset_id.slice(0, 8)}
                  {frame.position_label_name ? ` · ${frame.position_label_name}` : ''}
                  {frame.effective_assignment_summaries[0]
                    ? ` — ${frame.effective_assignment_summaries[0]}`
                    : ''}
                </Text>
              ))}
            </View>
          ) : null}
        </>
      ) : (
        <Text style={styles.muted}>Cargando vista operativa…</Text>
      )}
    </View>
  );
}
