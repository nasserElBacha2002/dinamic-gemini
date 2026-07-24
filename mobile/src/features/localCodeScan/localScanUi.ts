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
      return 'Código detectado localmente (borrador; el servidor confirma)';
    case 'UNRESOLVED':
      return 'Sin código detectado — se procesará en servidor';
    case 'INVALID':
      return 'Código local inválido — se procesará en servidor';
    case 'AMBIGUOUS':
      return 'Código ambiguo — se procesará en servidor';
    case 'FAILED':
      return 'Error local — se procesará en servidor';
    default:
      return null;
  }
}
