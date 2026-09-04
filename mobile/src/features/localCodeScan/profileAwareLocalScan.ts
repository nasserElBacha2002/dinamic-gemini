/**
 * Apply Dinamic consolidator first, then supplier offline profiles for non-D1 leftovers.
 */

import { consolidateCodeDetections, type DetectedCodeCandidate } from '../../core/codeDetectionConsolidator';
import { parseProductLabelPayload } from '../../core/productLabelFormat';
import {
  validateSupplierPayloadOffline,
  type LocalRecognitionResult,
} from '../../core/offlineSupplierLabelValidator';
import type { LocalLabelProfileResolver } from '../offlineRecognition/localLabelProfileResolver';

export interface ProfileAwareScanOutcome {
  readonly consolidation: ReturnType<typeof consolidateCodeDetections>;
  readonly supplierItem: LocalRecognitionResult | null;
  readonly supplierPosition: LocalRecognitionResult | null;
  readonly ambiguous: boolean;
  /** @deprecated Prefer itemProfileMissing / positionProfileMissing. */
  readonly profileMissing: boolean;
  readonly itemProfileMissing: boolean;
  readonly positionProfileMissing: boolean;
  readonly recognitionSnapshot: Record<string, unknown> | null;
}

export async function runProfileAwareLocalScan(input: {
  candidates: readonly DetectedCodeCandidate[];
  inventoryId: string | null;
  aisleId: string | null;
  resolver: LocalLabelProfileResolver | null;
  offline: boolean;
}): Promise<ProfileAwareScanOutcome> {
  const consolidation = consolidateCodeDetections(input.candidates);
  if (!input.resolver || !input.inventoryId || !input.aisleId) {
    return {
      consolidation,
      supplierItem: null,
      supplierPosition: null,
      ambiguous: false,
      profileMissing: false,
      itemProfileMissing: false,
      positionProfileMissing: false,
      recognitionSnapshot: null,
    };
  }

  const profiles = await input.resolver.resolveForAisle(input.inventoryId, input.aisleId);
  const itemProfileMissing = profiles.item.missingSupplierProfile;
  const positionProfileMissing = profiles.position.missingSupplierProfile;

  // Fail-closed Dinamic: keep consolidator outcome for D1 / Dinamic position.
  let supplierItem: LocalRecognitionResult | null = null;
  let supplierPosition: LocalRecognitionResult | null = null;

  if (
    !consolidation.d1Mode &&
    !itemProfileMissing &&
    profiles.item.source === 'SUPPLIER' &&
    profiles.item.profile &&
    profiles.item.configuration
  ) {
    for (const c of input.candidates) {
      const d1 = parseProductLabelPayload(c.rawValue);
      if (d1.status !== 'NOT_OUR_FORMAT' && d1.status !== 'UNKNOWN_VERSION') {
        // Looks like D1 — leave to consolidator / fail-closed path.
        continue;
      }
      const result = validateSupplierPayloadOffline({
        rawPayload: c.rawValue,
        labelKind: 'ITEM',
        configuration: profiles.item.configuration,
        profileId: profiles.item.profile.profile_id,
        profileVersion: profiles.item.profile.profile_version,
      });
      if (result.status === 'VALID') {
        supplierItem = result;
        break;
      }
      if (result.status === 'INVALID') {
        supplierItem = result;
        break;
      }
      // NOT_APPLICABLE → try next candidate
    }
  }

  if (
    !positionProfileMissing &&
    profiles.position.source === 'SUPPLIER' &&
    profiles.position.profile &&
    profiles.position.configuration
  ) {
    for (const c of input.candidates) {
      const result = validateSupplierPayloadOffline({
        rawPayload: c.rawValue,
        labelKind: 'POSITION',
        configuration: profiles.position.configuration,
        profileId: profiles.position.profile.profile_id,
        profileVersion: profiles.position.profile.profile_version,
      });
      if (result.status === 'VALID') {
        supplierPosition = result;
        break;
      }
    }
  }

  const ambiguous =
    Boolean(supplierItem?.status === 'VALID') &&
    Boolean(supplierPosition?.status === 'VALID') &&
    supplierItem?.normalizedPayload === supplierPosition?.normalizedPayload;

  const recognitionSnapshot = {
    offline: input.offline,
    client_supplier_id:
      profiles.item.clientSupplierId ?? profiles.position.clientSupplierId ?? null,
    item_profile_missing: itemProfileMissing,
    position_profile_missing: positionProfileMissing,
    item: supplierItem
      ? {
          status: supplierItem.status,
          error_code: supplierItem.errorCode,
          profile_id: supplierItem.profileId,
          profile_version: supplierItem.profileVersion,
          profile_source: supplierItem.profileSource,
          configuration_schema_version: supplierItem.configurationSchemaVersion,
          label_id: supplierItem.labelId,
          sku: supplierItem.sku,
          quantity: supplierItem.quantity,
        }
      : {
          profile_source: profiles.item.source,
          profile_id: profiles.item.profile?.profile_id ?? null,
          profile_version: profiles.item.profile?.profile_version ?? null,
          configuration_schema_version: profiles.item.profile?.configuration_schema_version ?? null,
          missing: itemProfileMissing,
        },
    position: supplierPosition
      ? {
          status: supplierPosition.status,
          error_code: supplierPosition.errorCode,
          profile_id: supplierPosition.profileId,
          profile_version: supplierPosition.profileVersion,
          profile_source: supplierPosition.profileSource,
          position_id: supplierPosition.positionId,
          pallet: supplierPosition.pallet,
          side: supplierPosition.side,
          level: supplierPosition.level,
        }
      : {
          profile_source: profiles.position.source,
          profile_id: profiles.position.profile?.profile_id ?? null,
          profile_version: profiles.position.profile?.profile_version ?? null,
          missing: positionProfileMissing,
        },
    ambiguous,
  };

  return {
    consolidation,
    supplierItem,
    supplierPosition,
    ambiguous,
    profileMissing: itemProfileMissing || positionProfileMissing,
    itemProfileMissing,
    positionProfileMissing,
    recognitionSnapshot,
  };
}
