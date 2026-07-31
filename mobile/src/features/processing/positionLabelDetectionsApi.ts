/**
 * Phase 3 — query job position-label detections (read-only).
 */

import type { ApiClient } from '../../services/api/apiClient';

export interface ImagePositionDetectionDto {
  readonly id: string;
  readonly asset_id: string;
  readonly sequence_number: number | null;
  readonly status: string;
  readonly signature_status: string;
  readonly position_label: {
    readonly id: string | null;
    readonly name: string | null;
    readonly public_identifier: string | null;
  } | null;
  readonly confidence: number | null;
  readonly detector_version: string;
  readonly created_at: string;
}

export interface ImagePositionDetectionListResponse {
  readonly items: readonly ImagePositionDetectionDto[];
}

export class PositionLabelDetectionsApi {
  constructor(private readonly api: ApiClient) {}

  async listForJob(
    inventoryId: string,
    jobId: string,
  ): Promise<ImagePositionDetectionListResponse> {
    return this.api.get<ImagePositionDetectionListResponse>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/jobs/${encodeURIComponent(jobId)}/position-detections`,
    );
  }
}

export function formatPositionDetectionLine(item: ImagePositionDetectionDto): string {
  const seq =
    item.sequence_number != null ? `Foto ${item.sequence_number}` : `Asset ${item.asset_id.slice(0, 8)}`;
  if (item.status === 'VALID' && item.position_label?.name) {
    return `${seq} — Posición ${item.position_label.name}`;
  }
  if (item.status === 'NO_LABEL') {
    return `${seq} — Sin código de posición`;
  }
  return `${seq} — ${item.status}`;
}
