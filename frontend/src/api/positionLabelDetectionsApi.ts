/**
 * Phase 3 — query position-label detections for a job (no product binding).
 */

import { apiRequestJson } from './request';

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
  return apiRequestJson<ImagePositionDetectionListResponse>(
    `/api/v3/inventories/${encodeURIComponent(inventoryId)}/jobs/${encodeURIComponent(jobId)}/position-detections`,
  );
}

export function labelForPositionDetectionStatus(status: string): string {
  switch (status) {
    case 'VALID':
      return 'Etiqueta de posicionamiento';
    case 'NO_LABEL':
      return 'Sin etiqueta de posición';
    case 'CLIENT_MISMATCH':
      return 'Etiqueta de otro cliente';
    case 'LABEL_INVALIDATED':
      return 'Etiqueta invalidada';
    case 'INVALID_SIGNATURE':
    case 'MISSING_SIGNATURE':
    case 'UNKNOWN_KEY_VERSION':
      return 'Etiqueta inválida (firma)';
    case 'UNSUPPORTED_LEGACY_PAYLOAD':
    case 'UNSUPPORTED_VERSION':
    case 'INVALID_TYPE':
    case 'INVALID_JSON':
      return 'Payload no soportado';
    case 'AMBIGUOUS_POSITION_DETECTION':
      return 'Detección ambigua';
    case 'SIGNATURE_VALIDATION_SKIPPED':
      return 'Firma no validada';
    case 'LABEL_NOT_FOUND':
      return 'Etiqueta desconocida';
    default:
      return status;
  }
}
