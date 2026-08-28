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
  payload_version?: number | null;
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
export function labelForPositionDetectionStatus(
  status: string,
  metadata?: Record<string, unknown>,
): string {
  const detail =
    metadata && typeof metadata.detail === 'string' && metadata.detail.trim()
      ? metadata.detail.trim()
      : null;
  switch (status) {
    case 'VALID':
      return 'Firma válida — posición resuelta';
    case 'LEGACY_UNSIGNED_REQUIRES_REVIEW':
      return 'Sin firma — requiere revisión';
    case 'NO_LABEL':
    case 'FEATURE_DISABLED':
      return 'Sin etiqueta de posición';
    case 'CLIENT_MISMATCH':
      return 'Etiqueta detectada, no resuelta: otro cliente';
    case 'LABEL_INVALIDATED':
      return 'Etiqueta detectada, no resuelta: invalidada';
    case 'INVALID_SIGNATURE':
      return detail
        ? `Etiqueta detectada, no resuelta: firma inválida (${detail})`
        : 'Etiqueta detectada, no resuelta: firma inválida';
    case 'MISSING_SIGNATURE':
      return 'Etiqueta detectada, no resuelta: firma ausente';
    case 'UNKNOWN_KEY_VERSION':
      return 'Etiqueta detectada, no resuelta: key_version desconocida';
    case 'UNSUPPORTED_LEGACY_PAYLOAD':
      return detail
        ? `Etiqueta detectada, no resuelta: payload legacy (${detail})`
        : 'Etiqueta detectada, no resuelta: payload legacy';
    case 'UNSUPPORTED_VERSION':
      return detail
        ? `Etiqueta detectada, no resuelta: versión no soportada (${detail})`
        : 'Etiqueta detectada, no resuelta: versión no soportada';
    case 'INVALID_TYPE':
      return detail
        ? `Etiqueta detectada, no resuelta: tipo/campos inválidos (${detail})`
        : 'Etiqueta detectada, no resuelta: tipo inválido';
    case 'INVALID_JSON':
      return 'Etiqueta detectada, no resuelta: JSON inválido';
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
      return `Estado de etiqueta de posición: ${trimmed}`;
    }
  }
}

export function formatPositionDetectionSecondary(args: {
  status: string;
  signatureStatus: string;
  labelId?: string | null;
  version?: string | null;
  assetId: string;
  metadata?: Record<string, unknown>;
}): string {
  const meta = args.metadata ?? {};
  const lines: string[] = [
    `Asset ID: ${args.assetId}`,
    `Estado: ${args.status}`,
    `Firma: ${args.signatureStatus}`,
  ];
  if (args.version) lines.push(`Versión: ${args.version}`);
  if (args.labelId) lines.push(`Label ID: ${args.labelId}`);
  const pallet = meta.pallet;
  const side = meta.side;
  const level = meta.level;
  const markerIndex = meta.marker_index;
  const markerTotal = meta.marker_total;
  if (pallet != null || side != null || level != null) {
    const marker =
      markerIndex != null && markerTotal != null
        ? `${String(markerIndex).padStart(2, '0')}/${String(markerTotal).padStart(2, '0')}`
        : null;
    lines.push(
      [
        pallet != null ? `Pallet ${pallet}` : null,
        side != null ? String(side) : null,
        level != null ? `Level ${level}` : null,
        marker,
      ]
        .filter(Boolean)
        .join(' · ')
    );
  }
  if (typeof meta.detail === 'string' && meta.detail.trim()) {
    lines.push(`Motivo: ${meta.detail.trim()}`);
  }
  const policyDecision = meta.policy_decision;
  if (typeof policyDecision === 'string' && policyDecision.trim()) {
    lines.push(`Política: ${policyDecision.trim()}`);
  }
  if (meta.requires_review === true) {
    lines.push('Requiere revisión: sí');
  }
  return lines.join('\n');
}
