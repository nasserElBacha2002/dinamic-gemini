/**
 * Single source of truth for mapping remote processing statuses to local persistence.
 */

import type { CaptureSessionStatus } from '../domain/enums/photoStatus';
import type { ProcessingJobLocalStatus } from '../domain/enums/uploadStatus';
import { mapRemoteJobStatus } from './captureState';

export type ProcessingState =
  | 'idle'
  | 'starting'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'unknown';

export interface ProcessingStateMapping {
  readonly state: ProcessingState;
  readonly jobStatus: ProcessingJobLocalStatus;
  readonly captureStatus: CaptureSessionStatus;
  readonly terminal: boolean;
}

export function toProcessingState(remote: string | null | undefined): ProcessingState {
  if (remote == null || remote.trim() === '' || remote === 'idle') {
    return 'idle';
  }
  const s = remote.trim().toLowerCase();
  if (s === 'starting') return 'starting';
  if (s === 'queued' || s === 'pending') return 'queued';
  if (s === 'running' || s === 'processing' || s === 'cancel_requested') return 'processing';
  if (s === 'succeeded' || s === 'completed' || s === 'success') return 'completed';
  if (s === 'failed' || s === 'timed_out' || s === 'error') return 'failed';
  if (s === 'canceled' || s === 'cancelled') return 'cancelled';
  const mapped = mapRemoteJobStatus(s);
  if (mapped === 'pending') return 'queued';
  if (mapped === 'running') return 'processing';
  if (mapped === 'success') return 'completed';
  if (mapped === 'failed') return 'failed';
  if (mapped === 'cancelled') return 'cancelled';
  return 'unknown';
}

export function mapProcessingPersistence(remoteStatus: string): ProcessingStateMapping {
  const state = toProcessingState(remoteStatus);
  switch (state) {
    case 'completed':
      return {
        state,
        jobStatus: 'success',
        captureStatus: 'completed',
        terminal: true,
      };
    case 'failed':
      return {
        state,
        jobStatus: 'failed',
        captureStatus: 'failed_processing',
        terminal: true,
      };
    case 'cancelled':
      return {
        state,
        jobStatus: 'cancelled',
        captureStatus: 'failed_processing',
        terminal: true,
      };
    case 'starting':
      return {
        state,
        jobStatus: 'pending',
        captureStatus: 'processing',
        terminal: false,
      };
    case 'queued':
      return {
        state,
        jobStatus: 'pending',
        captureStatus: 'processing',
        terminal: false,
      };
    case 'processing':
      return {
        state,
        jobStatus: 'running',
        captureStatus: 'processing',
        terminal: false,
      };
    case 'unknown':
      return {
        state,
        jobStatus: 'unknown',
        captureStatus: 'processing',
        terminal: false,
      };
    case 'idle':
    default:
      return {
        state: 'idle',
        jobStatus: 'pending',
        captureStatus: 'ready_to_process',
        terminal: false,
      };
  }
}

export function processingStateLabel(state: ProcessingState): string {
  switch (state) {
    case 'idle':
      return 'Sin iniciar';
    case 'starting':
      return 'Iniciando';
    case 'queued':
      return 'En cola';
    case 'processing':
      return 'Procesando';
    case 'completed':
      return 'Completado';
    case 'failed':
      return 'Falló';
    case 'cancelled':
      return 'Cancelado';
    case 'unknown':
      return 'Estado desconocido';
    default:
      return 'Desconocido';
  }
}

export function processingStateLabelFromRemote(remote: string | null | undefined): string {
  return processingStateLabel(toProcessingState(remote));
}

export function primaryProcessingAction(
  state: ProcessingState,
): 'process' | 'busy' | 'view_result' | 'retry' | 'refresh' | 'none' {
  switch (state) {
    case 'idle':
      return 'process';
    case 'starting':
    case 'queued':
    case 'processing':
      return 'busy';
    case 'completed':
      return 'view_result';
    case 'failed':
      return 'retry';
    case 'cancelled':
      return 'process';
    case 'unknown':
      return 'refresh';
    default:
      return 'none';
  }
}

export function primaryProcessingActionLabel(state: ProcessingState): string {
  switch (primaryProcessingAction(state)) {
    case 'process':
      return state === 'cancelled' ? 'Procesar nuevamente' : 'Procesar pasillo';
    case 'busy':
      if (state === 'starting') return 'Iniciando…';
      if (state === 'queued') return 'En cola';
      return 'Procesando…';
    case 'view_result':
      return 'Ver resultado';
    case 'retry':
      return 'Reintentar procesamiento';
    case 'refresh':
      return 'Actualizar estado';
    default:
      return 'Procesar pasillo';
  }
}
