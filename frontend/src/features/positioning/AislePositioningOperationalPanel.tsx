/**
 * Phase 7 — aisle positioning operational summary driven by backend authority.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material';
import { recoverAisleProcessing } from '../../api/aislesApi';
import {
  getAislePositioningOperationalView,
  getAislePositioningSequence,
  reprocessAislePositioning,
  type AisleOperationalPositioningViewDto,
  type PositioningSequenceFrameDto,
} from '../../api/positioningOperationalApi';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import {
  ACTIVE_POLLING_STATES,
  presentationForProcessingState,
} from './processingStateLabels';

function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function modeLabel(mode: string): string {
  if (mode === 'RECONCILE_ONLY') return 'Solo reconciliar';
  if (mode === 'REPROCESS_FULL_AISLE') return 'Pasillo completo';
  return mode;
}

export interface AislePositioningOperationalPanelProps {
  inventoryId: string;
  aisleId: string;
  jobId?: string | null;
  onJobChanged?: (jobId: string | null) => void;
  onProcessRequested?: () => void;
}

export default function AislePositioningOperationalPanel({
  inventoryId,
  aisleId,
  jobId,
  onJobChanged,
  onProcessRequested,
}: AislePositioningOperationalPanelProps) {
  const [view, setView] = useState<AisleOperationalPositioningViewDto | null>(null);
  const [sequence, setSequence] = useState<PositioningSequenceFrameDto[]>([]);
  const [sequenceTotal, setSequenceTotal] = useState(0);
  const [sequencePage, setSequencePage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const [reprocessMode, setReprocessMode] = useState('REPROCESS_FULL_AISLE');
  const idempotencyRef = useRef(newIdempotencyKey('pos-reprocess'));
  const mounted = useRef(true);

  const loadSequence = useCallback(
    async (resultJob: string, page: number, append: boolean) => {
      const seq = await getAislePositioningSequence(inventoryId, aisleId, resultJob, page, 30);
      if (!mounted.current) return;
      setSequenceTotal(seq.total);
      setSequencePage(seq.page);
      setSequence((prev) => (append ? [...prev, ...seq.items] : seq.items));
    },
    [inventoryId, aisleId],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await getAislePositioningOperationalView(inventoryId, aisleId, jobId);
      if (!mounted.current) return;
      setView(next);
      const resultJob = next.result_job_id;
      if (resultJob && next.feature_flags.POSITION_OPERATIONAL_UX_ENABLED !== false) {
        await loadSequence(resultJob, 1, false);
      } else if (mounted.current) {
        setSequence([]);
        setSequenceTotal(0);
      }
    } catch (e) {
      if (mounted.current) setError(getVisibleErrorMessage(e));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [inventoryId, aisleId, jobId, loadSequence]);

  useEffect(() => {
    mounted.current = true;
    setLoading(true);
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  useEffect(() => {
    if (!view || !ACTIVE_POLLING_STATES.has(view.processing_state)) return;
    const schedule = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return undefined;
      }
      return window.setTimeout(() => {
        void load();
      }, 4000);
    };
    let handle = schedule();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        void load();
        if (handle) window.clearTimeout(handle);
        handle = schedule();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      if (handle) window.clearTimeout(handle);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [view, load]);

  const presentation = useMemo(
    () =>
      presentationForProcessingState(view?.processing_state ?? 'IDLE', {
        scannerTxtImport: Boolean(view?.has_dinamic_scanner_txt_import),
      }),
    [view?.processing_state, view?.has_dinamic_scanner_txt_import],
  );

  const onRecover = async () => {
    if (!view?.allowed_actions.recover) return;
    setBusy(true);
    setError(null);
    try {
      await recoverAisleProcessing(inventoryId, aisleId, {
        reason: 'web_positioning_operational_panel',
      });
      await load();
    } catch (e) {
      setError(getVisibleErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const onConfirmReprocess = async () => {
    if (!view) return;
    setBusy(true);
    setError(null);
    try {
      const result = await reprocessAislePositioning(inventoryId, aisleId, {
        idempotency_key: idempotencyRef.current,
        reprocess_mode: reprocessMode,
        expected_active_job_id: view.active_job_id,
        expected_result_job_id: view.result_job_id,
        identification_mode: null,
      });
      idempotencyRef.current = newIdempotencyKey('pos-reprocess');
      setReprocessOpen(false);
      onJobChanged?.(result.job_id);
      await load();
    } catch (e) {
      setError(getVisibleErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !view) {
    return (
      <Box sx={{ py: 2, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  if (!view) {
    return error ? <Alert severity="error">{error}</Alert> : null;
  }

  if (view.feature_flags.POSITION_OPERATIONAL_UX_ENABLED === false) {
    return null;
  }

  const overridePolicyHint =
    reprocessMode === 'RECONCILE_ONLY'
      ? 'Las correcciones manuales se conservan porque el job y los result IDs no cambian.'
      : 'Un reproceso completo crea un job nuevo: las correcciones manuales del job anterior requieren revisión (no se migran automáticamente).';

  return (
    <Box
      component="section"
      aria-label="Estado operativo de posicionamiento"
      sx={{ mb: 2, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
    >
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
        <Box>
          <Typography variant="h6" component="h2">
            Posicionamiento operativo
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {presentation.description}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', gap: 1 }}>
            <Chip label={presentation.label} color="primary" size="small" />
            {view.reconciliation_status ? (
              <Chip label={`Reconciliación: ${view.reconciliation_status}`} size="small" />
            ) : null}
            <Chip label={`Productos: ${view.total_results}`} size="small" variant="outlined" />
            <Chip label={`Con posición: ${view.assigned_results}`} size="small" variant="outlined" />
            <Chip label={`Sin posición: ${view.unassigned_results}`} size="small" variant="outlined" />
            <Chip label={`Manuales: ${view.manual_overrides_count}`} size="small" variant="outlined" />
            <Chip label={`Detecciones: ${view.detections_count}`} size="small" variant="outlined" />
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap">
          {view.allowed_actions.process ? (
            <Button variant="contained" disabled={busy} onClick={() => onProcessRequested?.()}>
              Procesar
            </Button>
          ) : null}
          {view.allowed_actions.recover ? (
            <Button variant="contained" color="warning" disabled={busy} onClick={() => void onRecover()}>
              Recuperar procesamiento
            </Button>
          ) : null}
          {view.allowed_actions.reprocess || view.allowed_actions.reconcile_only ? (
            <Button
              variant="outlined"
              disabled={busy}
              onClick={() => {
                const modes = view.supported_reprocess_modes;
                setReprocessMode(modes[0] ?? 'REPROCESS_FULL_AISLE');
                setReprocessOpen(true);
              }}
            >
              Reprocesar
            </Button>
          ) : null}
          <Button variant="text" disabled={busy} onClick={() => void load()}>
            Actualizar
          </Button>
        </Stack>
      </Stack>

      {error ? (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      ) : null}

      {view.warnings.length > 0 ? (
        <Stack spacing={1} sx={{ mt: 2 }}>
          {view.warnings.map((w) => (
            <Alert
              key={w.code}
              severity={w.severity === 'ERROR' ? 'error' : w.severity === 'WARNING' ? 'warning' : 'info'}
            >
              <strong>{w.title}</strong> — {w.description}
              {w.affected_count > 0 ? ` (${w.affected_count})` : ''}
            </Alert>
          ))}
        </Stack>
      ) : null}

      {view.unassigned_by_cause.length > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">Sin posición por causa</Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {view.unassigned_by_cause.map((b) => (
              <Typography key={b.cause} variant="body2">
                {b.cause}: {b.count} — sugerido: {b.suggested_action}
              </Typography>
            ))}
          </Stack>
        </Box>
      ) : null}

      {sequence.length > 0 || sequenceTotal > 0 ? (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">
            Secuencia ({sequence.length} de {sequenceTotal})
          </Typography>
          <Stack spacing={0.75} sx={{ mt: 1, maxHeight: 240, overflow: 'auto' }}>
            {sequence.map((frame) => (
              <Box key={`${frame.source_asset_id}-${frame.sequence_number ?? 'x'}`} sx={{ display: 'flex', gap: 1 }}>
                <Typography variant="body2" sx={{ minWidth: 28 }}>
                  {frame.sequence_number ?? '—'}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                  {frame.filename || frame.source_asset_id.slice(0, 8)}
                  {frame.position_label_name ? ` · ${frame.position_label_name}` : ''}
                  {frame.effective_assignment_summaries[0]
                    ? ` — ${frame.effective_assignment_summaries[0]}`
                    : frame.transition_message
                      ? ` — ${frame.transition_message}`
                      : ''}
                </Typography>
              </Box>
            ))}
          </Stack>
          {sequence.length < sequenceTotal && view.result_job_id ? (
            <Button
              size="small"
              sx={{ mt: 1 }}
              disabled={busy}
              onClick={() => void loadSequence(view.result_job_id as string, sequencePage + 1, true)}
            >
              Cargar más
            </Button>
          ) : null}
        </Box>
      ) : null}

      <Dialog open={reprocessOpen} onClose={() => !busy && setReprocessOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Confirmar reprocesamiento</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Tipo: {modeLabel(reprocessMode)}
          </Typography>
          <Typography variant="body2">Productos: {view.total_results}</Typography>
          <Typography variant="body2">
            Correcciones manuales activas: {view.manual_overrides_count}
          </Typography>
          <Typography variant="body2">Último job: {view.result_job_id ?? '—'}</Typography>
          <Alert severity={reprocessMode === 'RECONCILE_ONLY' ? 'info' : 'warning'} sx={{ mt: 2 }}>
            {overridePolicyHint}
          </Alert>
          {view.supported_reprocess_modes.length > 1 ? (
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              {view.supported_reprocess_modes.map((mode) => (
                <Button
                  key={mode}
                  size="small"
                  variant={reprocessMode === mode ? 'contained' : 'outlined'}
                  onClick={() => {
                    setReprocessMode(mode);
                    idempotencyRef.current = newIdempotencyKey('pos-reprocess');
                  }}
                >
                  {modeLabel(mode)}
                </Button>
              ))}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setReprocessOpen(false)}>
            Cancelar
          </Button>
          <Button variant="contained" disabled={busy} onClick={() => void onConfirmReprocess()}>
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
