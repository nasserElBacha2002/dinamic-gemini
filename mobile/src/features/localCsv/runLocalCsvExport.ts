import type { LocalCsvExportService, ExportedLocalCsv } from './localCsvExportService';

export type LocalCsvExportUserError =
  | { kind: 'unresolved' }
  | { kind: 'no_products' }
  | { kind: 'empty' }
  | { kind: 'photo_read' }
  | { kind: 'share_unavailable' }
  | { kind: 'offline_config' }
  | { kind: 'scan_unsupported' }
  | { kind: 'photos_unstable' }
  | { kind: 'generic'; message: string };

export interface RunLocalCsvExportResult {
  readonly exported: ExportedLocalCsv;
  /** True when the share sheet was shown; cancel does not throw. */
  readonly shared: boolean;
}

/**
 * Shared export + share pipeline for Review / Local Activity.
 * Share cancellation must not invalidate the session (expo-sharing typically resolves).
 */
export async function runLocalCsvExport(
  service: LocalCsvExportService,
  sessionId: string,
  options: { share?: boolean } = {},
): Promise<RunLocalCsvExportResult> {
  const exported = await service.exportSession(sessionId);
  if (options.share === false) {
    return { exported, shared: false };
  }
  try {
    await service.shareExport(exported.fileUri, exported.exportId, exported.zipUri);
    return { exported, shared: true };
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    // User dismiss / cancel should not surface as a hard failure that blocks retries.
    if (/cancel|dismiss|User did not share/i.test(raw)) {
      return { exported, shared: false };
    }
    throw e;
  }
}

export function mapLocalCsvExportError(error: unknown): LocalCsvExportUserError {
  const raw = error instanceof Error ? error.message : String(error);
  if (raw.startsWith('PACKAGE_EXPORT_UNRESOLVED:')) {
    return { kind: 'unresolved' };
  }
  if (raw.startsWith('PACKAGE_EXPORT_OFFLINE_CONFIG_REQUIRED:')) {
    return { kind: 'offline_config' };
  }
  if (raw.startsWith('PACKAGE_EXPORT_SCAN_UNSUPPORTED:')) {
    return { kind: 'scan_unsupported' };
  }
  if (raw.startsWith('PACKAGE_EXPORT_PHOTOS_UNSTABLE:')) {
    return { kind: 'photos_unstable' };
  }
  if (raw.startsWith('PACKAGE_EXPORT_NO_PRODUCTS:')) {
    return { kind: 'no_products' };
  }
  if (raw.startsWith('PACKAGE_EXPORT_EMPTY:')) {
    return { kind: 'empty' };
  }
  if (raw.startsWith('PACKAGE_PHOTO_READ_FAILED:')) {
    return { kind: 'photo_read' };
  }
  if (/no permite compartir|Sharing is not available/i.test(raw)) {
    return { kind: 'share_unavailable' };
  }
  return { kind: 'generic', message: raw };
}

export function userMessageForLocalCsvExportError(error: LocalCsvExportUserError): string {
  switch (error.kind) {
    case 'unresolved':
      return 'No se pudo exportar: faltan códigos detectados en las fotos. Esperá el escaneo local o volvé a capturar etiquetas/SKU legibles (no requiere conexión al servidor).';
    case 'offline_config':
      return 'No se pudo exportar: falta la configuración offline del proveedor. Conectate a internet, abrí Pasillos y tocá «Actualizar configuración offline», luego reintentá el escaneo o la exportación.';
    case 'scan_unsupported':
      return 'No se pudo exportar: este dispositivo no puede escanear códigos localmente. Verificá que la app tenga el módulo de captura instalado (Android).';
    case 'photos_unstable':
      return 'No se pudo exportar: las fotos aún se están procesando. Esperá unos segundos y volvé a intentar.';
    case 'no_products':
      return 'No se pudo exportar: no hay productos con código interno. Escaneá al menos un SKU (las fotos de posición solas no alcanzan).';
    case 'empty':
      return 'No hay fotos para exportar.';
    case 'photo_read':
      return 'No se pudo leer una o más fotos del freeze. La captura sigue disponible; reintentá o verificá el almacenamiento.';
    case 'share_unavailable':
      return 'Este dispositivo no permite compartir archivos.';
    case 'generic':
      return error.message;
  }
}
