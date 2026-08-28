/** Map authoritative backend processing_state → operator-facing copy (ES). */

export interface ProcessingStatePresentation {
  label: string;
  description: string;
  primaryAction: string | null;
  secondaryAction: string | null;
}

const MAP: Record<string, ProcessingStatePresentation> = {
  IDLE: {
    label: 'Sin procesamiento',
    description: 'Este pasillo aún no tiene un job activo.',
    primaryAction: 'Procesar',
    secondaryAction: null,
  },
  PREPARING: {
    label: 'Preparando',
    description: 'Se está preparando el procesamiento.',
    primaryAction: null,
    secondaryAction: null,
  },
  UPLOADING: {
    label: 'Subiendo',
    description: 'Hay cargas en curso asociadas al pasillo.',
    primaryAction: null,
    secondaryAction: null,
  },
  STARTING: {
    label: 'Iniciando',
    description: 'El job está arrancando en el worker.',
    primaryAction: null,
    secondaryAction: null,
  },
  RUNNING: {
    label: 'En ejecución',
    description: 'El procesamiento está activo.',
    primaryAction: null,
    secondaryAction: null,
  },
  FINALIZING: {
    label: 'Finalizando',
    description: 'Se están persistiendo resultados y reconciliación.',
    primaryAction: null,
    secondaryAction: null,
  },
  COMPLETED: {
    label: 'Finalizado',
    description: 'El procesamiento terminó correctamente.',
    primaryAction: 'Revisar',
    secondaryAction: 'Reprocesar',
  },
  COMPLETED_WITH_WARNINGS: {
    label: 'Finalizado con observaciones',
    description: 'El job terminó, pero hay advertencias operativas.',
    primaryAction: 'Revisar',
    secondaryAction: 'Reprocesar',
  },
  FAILED: {
    label: 'Fallido',
    description: 'El procesamiento falló.',
    primaryAction: 'Reprocesar',
    secondaryAction: null,
  },
  CANCELED: {
    label: 'Cancelado',
    description: 'El procesamiento fue cancelado.',
    primaryAction: 'Procesar',
    secondaryAction: null,
  },
  TIMED_OUT: {
    label: 'Tiempo agotado',
    description: 'El job excedió el tiempo permitido.',
    primaryAction: 'Recuperar',
    secondaryAction: 'Reprocesar',
  },
  SUSPECTED_STALE: {
    label: 'Posiblemente estancado',
    description: 'El job parece detenido; espere o recupere si el backend lo autoriza.',
    primaryAction: null,
    secondaryAction: 'Actualizar',
  },
  RECOVERY_REQUIRED: {
    label: 'Recuperación requerida',
    description: 'El procesamiento quedó interrumpido antes de completar el worker.',
    primaryAction: 'Recuperar procesamiento',
    secondaryAction: null,
  },
};

export function presentationForProcessingState(
  state: string,
  options?: { scannerTxtImport?: boolean },
): ProcessingStatePresentation {
  if (options?.scannerTxtImport) {
    return {
      label: 'Importado de TXT',
      description:
        'Los resultados provienen de un archivo TXT del escáner; no requiere procesamiento CV.',
      primaryAction: null,
      secondaryAction: null,
    };
  }
  const key = (state || '').trim().toUpperCase();
  return (
    MAP[key] ?? {
      label: state || 'Desconocido',
      description: 'Estado de procesamiento reportado por el backend.',
      primaryAction: null,
      secondaryAction: null,
    }
  );
}

export const ACTIVE_POLLING_STATES = new Set([
  'PREPARING',
  'UPLOADING',
  'STARTING',
  'RUNNING',
  'FINALIZING',
  'RECOVERY_REQUIRED',
  'SUSPECTED_STALE',
]);
