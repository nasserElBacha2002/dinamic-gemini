/**
 * Session ZIP manifest (package_version 2).
 * Inventory rows are canonical in results.csv; legacy manifest fields mirror CSV for v2 consumers.
 */

import { CHECKSUM_ALGORITHM, LOCAL_CSV_SCHEMA_VERSION } from './csvFormat';
import { LOCAL_PACKAGE_KIND, LOCAL_PACKAGE_VERSION } from './localPackageContract';

export type SessionPackagePhotoManifestEntry = Record<string, unknown>;

export interface SessionPackageManifestSummary {
  readonly photo_count: number;
  readonly position_event_count: number;
  readonly product_result_count: number;
  readonly rejected_detection_count: number;
}

export interface BuildSessionPackageManifestInput {
  readonly csvSchemaVersion?: string;
  readonly exportId: string;
  readonly exportedAt: string;
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly captureSessionId: string;
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  readonly rowCount: number;
  readonly expectedPhotoCount: number;
  readonly includedPhotoCount: number;
  readonly csvChecksumSha256: string;
  readonly packageChecksumSha256: string;
  readonly positionEventCount: number;
  readonly productResultCount: number;
  readonly rejectedDetectionCount: number;
  readonly photos: readonly SessionPackagePhotoManifestEntry[];
}

export function buildSessionPackageManifest(
  input: BuildSessionPackageManifestInput,
): Record<string, unknown> {
  const summary: SessionPackageManifestSummary = {
    photo_count: input.includedPhotoCount,
    position_event_count: input.positionEventCount,
    product_result_count: input.productResultCount,
    rejected_detection_count: input.rejectedDetectionCount,
  };
  return {
    schema_version: input.csvSchemaVersion ?? LOCAL_CSV_SCHEMA_VERSION,
    package_kind: LOCAL_PACKAGE_KIND,
    package_version: LOCAL_PACKAGE_VERSION,
    status: 'COMPLETE',
    export_id: input.exportId,
    exported_at: input.exportedAt,
    inventory_id: input.inventoryId,
    aisle_id: input.aisleId,
    capture_session_id: input.captureSessionId,
    freeze_id: input.freezeId,
    freeze_generation: input.freezeGeneration,
    row_count: input.rowCount,
    expected_photo_count: input.expectedPhotoCount,
    included_photo_count: input.includedPhotoCount,
    missing_photos: [] as const,
    csv_checksum_sha256: input.csvChecksumSha256,
    checksum_sha256: input.csvChecksumSha256,
    checksum_algorithm: CHECKSUM_ALGORITHM,
    package_checksum_sha256: input.packageChecksumSha256,
    summary,
    photos: input.photos,
  };
}
