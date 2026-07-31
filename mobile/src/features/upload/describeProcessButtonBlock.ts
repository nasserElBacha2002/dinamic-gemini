/**
 * User-facing reason why «Procesar pasillo» stays disabled on UploadsScreen.
 * Local CODE_SCAN can succeed while uploads to the backend are still pending/failed.
 */

import type { CapturePhotoRow } from '../../database/schema/captureSchema';
import { LOCAL_DB_BUSY } from '../../core/uploadErrors';

export function describeProcessButtonBlock(input: {
  readonly ready: boolean;
  readonly photos: readonly CapturePhotoRow[];
  readonly pendingUploads: number;
  readonly uploadedCount: number;
}): string | null {
  if (input.ready) {
    return null;
  }
  const stable = input.photos.filter((p) => p.status === 'stable');
  const retryable = stable.filter((p) => p.upload_status === 'retryable_error');
  const permanent = stable.filter((p) => p.upload_status === 'permanent_error');
  const localDbBusy = [...retryable, ...permanent].some((p) => {
    const code = (p.last_upload_error_code ?? '').toUpperCase();
    const msg = (p.last_upload_error_message ?? '').toLowerCase();
    return (
      code === LOCAL_DB_BUSY ||
      msg.includes('database is locked') ||
      msg.includes('base local estaba ocupada')
    );
  });
  if (localDbBusy) {
    return (
      'La base local estaba ocupada al subir (cola/escaneo concurrente). ' +
      'Tocá «Reintentar todo» — no es un problema de red.'
    );
  }
  const backendUnreachable = [...retryable, ...permanent].some((p) => {
    const code = (p.last_upload_error_code ?? '').toUpperCase();
    const msg = (p.last_upload_error_message ?? '').toLowerCase();
    return (
      code === 'NETWORK_ERROR' ||
      code === 'REQUEST_TIMEOUT' ||
      msg.includes('no se pudo conectar') ||
      msg.includes('network') ||
      msg.includes('backend')
    );
  });

  if (backendUnreachable) {
    return (
      'No se pudo subir al backend (conexión). El escaneo local no basta para procesar: ' +
      'las fotos deben cargarse al servidor. Con API en 127.0.0.1 y USB, ejecutá ' +
      '`adb reverse tcp:8000 tcp:8000` y tocá «Reintentar todo».'
    );
  }
  if (permanent.length > 0) {
    return 'Hay errores permanentes de carga. Revisá las fotos marcadas y reintentá o excluilas.';
  }
  if (input.pendingUploads > 0) {
    return `Aún hay ${input.pendingUploads} carga(s) pendiente(s). El procesamiento se habilita cuando terminen.`;
  }
  if (input.uploadedCount === 0) {
    return 'Todavía no hay fotos cargadas en el servidor. Esperá la cola o reintentá.';
  }
  return 'El procesamiento se habilita cuando no queden cargas pendientes ni errores recuperables.';
}
