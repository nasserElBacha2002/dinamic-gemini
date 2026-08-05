/**
 * Phase 3 — query position-label detections for a job (no product binding).
 */

import { apiRequestJson } from './request';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

export interface PositionLabelSummaryDto {
  id: string | null;
  name: string | null;
  public_identifier: string | null;
}

export interface ImagePositionDetectionDto {
  id: string;
  asset_id: string;
  sequence_number: number | null;
  status: string;
  signature_status: string;
  position_label: PositionLabelSummaryDto | null;
  confidence: number | null;
  detector_version: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface ImagePositionDetectionListResponse {
  items: ImagePositionDetectionDto[];
}

export async function listJobPositionDetections(
  inventoryId: string,
  jobId: string,
): Promise<ImagePositionDetectionListResponse> {
  // Same API_BASE pattern as positioningOperationalApi / inventoriesApi —
  // apiRequestJson does not prepend VITE_API_BASE_URL.
  return apiRequestJson<ImagePositionDetectionListResponse>(
    `${API_BASE}/api/v3/inventories/${encodeURIComponent(inventoryId)}/jobs/${encodeURIComponent(jobId)}/position-detections`,
  );
}

/**
 * Display labels for detection_status enum values.
 * Does not invent "unresolved" copy for unknown statuses.
 * FEATURE_DISABLED / NO_LABEL = no operative position detection.
 */
export function labelForPositionDetectionStatus(status: string): string {
  switch (status) {
    case 'VALID':
      return 'Etiqueta de posicionamiento resuelta';
    case 'LEGACY_UNSIGNED_REQUIRES_REVIEW':
      return 'Etiqueta resuelta (sin firma; requiere revisión)';
    case 'NO_LABEL':
    case 'FEATURE_DISABLED':
      return 'Sin etiqueta de posición';
    case 'CLIENT_MISMATCH':
      return 'Etiqueta detectada, no resuelta: otro cliente';
    case 'LABEL_INVALIDATED':
      return 'Etiqueta detectada, no resuelta: invalidada';
    case 'INVALID_SIGNATURE':
    case 'MISSING_SIGNATURE':
    case 'UNKNOWN_KEY_VERSION':
      return 'Etiqueta detectada, no resuelta: firma';
    case 'UNSUPPORTED_LEGACY_PAYLOAD':
    case 'UNSUPPORTED_VERSION':
    case 'INVALID_TYPE':
    case 'INVALID_JSON':
      return 'Etiqueta detectada, no resuelta: payload no soportado';
    case 'AMBIGUOUS_POSITION_DETECTION':
    case 'DUPLICATE_POSITION_CODES':
      return 'Etiqueta detectada, no resuelta: ambigua';
    case 'SIGNATURE_VALIDATION_SKIPPED':
      return 'Etiqueta detectada, no resuelta: firma no validada';
    case 'LABEL_NOT_FOUND':
      return 'Etiqueta detectada, no resuelta: desconocida';
    case 'MISSING_LABEL_ID':
      return 'Etiqueta detectada, no resuelta: sin identificador';
    case 'PAYLOAD_TOO_LARGE':
      return 'Etiqueta detectada, no resuelta: payload demasiado grande';
    case 'DECODE_TIMEOUT':
      return 'Etiqueta detectada, no resuelta: timeout de decodificación';
    case 'DETECTION_FAILED':
      return 'Etiqueta detectada, no resuelta: detección fallida';
    case 'DETECTION_CONTEXT_INVALID':
      return 'Etiqueta detectada, no resuelta: contexto inválido';
    default: {
      const trimmed = (status || '').trim();
      if (!trimmed) {
        return 'Sin etiqueta de posición';
      }
      return `Estado de detección desconocido: ${trimmed}`;
    }
  }
}
