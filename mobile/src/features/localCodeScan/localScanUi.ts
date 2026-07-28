import type { LocalDetectionDraftRow } from '../../database/repositories/localDetectionDraftRepository';
import type { LocalDetectionDraftStatus } from '../../database/repositories/localDetectionDraftRepository';

/** Operational-only copy — never presents local result as authoritative. */
export function labelForLocalScanStatus(status: LocalDetectionDraftStatus | null | undefined): string | null {
  if (!status || status === 'NOT_APPLICABLE') {
    return null;
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
      return 'Código local inválido — se procesará en servidor';
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
  'status' | 'internal_code' | 'quantity' | 'error_code' | 'detected_symbology'
> | null | undefined): string | null {
  if (!draft || draft.status === 'NOT_APPLICABLE') {
    return null;
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
