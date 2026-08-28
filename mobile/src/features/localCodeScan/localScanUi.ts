import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { LocalDetectionDraftStatus } from '../../database/repositories/localDetectionDraftRepository';
import { parseStoredProductRejections } from '../../core/productLabelRejection';

function friendlyD1RejectionMessage(
  rejectionsJson: string | null | undefined,
): string | null {
  const rejections = parseStoredProductRejections(rejectionsJson);
  if (!rejections.length) return null;
  const status = rejections[0]!.validationStatus.toUpperCase();
  if (status.includes('CHECKSUM')) {
    return 'Etiqueta inválida: checksum incorrecto';
  }
  if (status.includes('MALFORMED')) {
    return 'Etiqueta Dinamic inválida';
  }
  if (status.includes('UNKNOWN_VERSION')) {
    return 'Etiqueta Dinamic: versión no soportada';
  }
  return 'Etiqueta Dinamic inválida';
}

/** Operational-only copy — never presents local result as authoritative. */
export function labelForLocalScanStatus(
  status: LocalDetectionDraftStatus | null | undefined,
  errorCode?: string | null,
  rejectionsJson?: string | null,
): string | null {
  if (!status || status === 'NOT_APPLICABLE') {
    return null;
  }
  if (errorCode === 'POSITION_LABEL_DUPLICATE') {
    return 'Etiqueta de posición duplicada — ya registrada en esta sesión';
  }
  if (errorCode === 'POSITION_LABEL_DETECTED') {
    return 'Etiqueta de posición detectada — se resolverá en servidor';
  }
  if (errorCode === 'D1_CANDIDATES_FAILED') {
    return (
      friendlyD1RejectionMessage(rejectionsJson) ??
      'Etiqueta Dinamic inválida — se procesará en servidor'
    );
  }
  switch (status) {
    case 'PENDING':
    case 'SCANNING':
      return 'Escaneando código localmente';
    case 'RESOLVED':
      return 'Código detectado localmente (borrador)';
    case 'DETECTED_UNVERIFIED':
      return 'Código no verificable localmente — se procesará en servidor';
    case 'UNRESOLVED':
      return 'Sin código detectado — se procesará en servidor';
    case 'INVALID':
      return (
        friendlyD1RejectionMessage(rejectionsJson) ??
        'Código local inválido — se procesará en servidor'
      );
    case 'AMBIGUOUS':
      return 'Código ambiguo — se procesará en servidor';
    case 'FAILED':
    case 'FAILED_RETRYABLE':
      return 'Error local — se procesará en servidor';
    default:
      return null;
  }
}

export function formatLocalScanDetection(draft: Pick<
  LocalDetectionDraftRow,
  'status' | 'internal_code' | 'quantity' | 'error_code' | 'detected_symbology' | 'rejections_json'
> | null | undefined): string | null {
  if (!draft || draft.status === 'NOT_APPLICABLE') {
    return null;
  }
  if (draft.error_code === 'POSITION_LABEL_DUPLICATE') {
    return 'Posición duplicada en sesión';
  }
  if (draft.error_code === 'POSITION_LABEL_DETECTED') {
    const code = draft.internal_code?.trim();
    if (code) {
      return draft.detected_symbology
        ? `${draft.detected_symbology} · Posición ${code}`
        : `Posición ${code}`;
    }
    return draft.detected_symbology
      ? `${draft.detected_symbology} · Etiqueta de posición`
      : 'Etiqueta de posición';
  }
  if (
    draft.error_code === 'D1_CANDIDATES_FAILED' ||
    (draft.status === 'INVALID' && draft.rejections_json)
  ) {
    const friendly = friendlyD1RejectionMessage(draft.rejections_json);
    if (friendly) return friendly;
  }
  const parts: string[] = [];
  if (draft.internal_code) {
    parts.push(`Código: ${draft.internal_code}`);
  }
  if (draft.quantity != null) {
    parts.push(`Cant: ${draft.quantity}`);
  }
  if (draft.detected_symbology) {
    parts.push(draft.detected_symbology);
  }
  if (draft.error_code && !draft.internal_code) {
    parts.push(`Error: ${draft.error_code}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

export function labelForPreliminarySyncStatus(
  syncStatus: string | null | undefined,
): string | null {
  switch (syncStatus) {
    case 'PENDING':
    case 'NOT_READY':
      return 'Borrador local pendiente de sincronización';
    case 'SYNCING':
      return 'Sincronizando borrador local';
    case 'SYNCED':
      return 'Borrador sincronizado';
    case 'RETRY_SCHEDULED':
      return 'Sincronización reintentando';
    case 'REJECTED':
      return 'Borrador rechazado';
    case 'CONFLICT':
      return 'Conflicto de sincronización';
    case 'FAILED_TERMINAL':
      return 'Sincronización fallida';
    default:
      return null;
  }
}
