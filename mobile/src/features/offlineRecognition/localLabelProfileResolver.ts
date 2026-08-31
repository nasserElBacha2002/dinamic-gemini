import type {
  OfflineRecognitionConfigRepository,
  OfflineRecognitionProfileRow,
} from '../../database/repositories/offlineRecognitionConfigRepository';
import type { OfflineExtractionConfiguration } from '../../core/offlineSupplierLabelValidator';

export type ResolvedLocalProfileSource = 'DINAMIC' | 'SUPPLIER';

export interface ResolvedLocalLabelProfile {
  readonly labelKind: 'ITEM' | 'POSITION';
  readonly source: ResolvedLocalProfileSource;
  readonly resolutionSource: 'AISLE_OVERRIDE' | 'CLIENT_SUPPLIER' | 'DEFAULT';
  readonly clientSupplierId: string | null;
  readonly profile: OfflineRecognitionProfileRow | null;
  readonly configuration: OfflineExtractionConfiguration | null;
  readonly missingSupplierProfile: boolean;
}

/**
 * Precedence matches backend LabelProfileResolver:
 * 1. aisle override
 * 2. effective source from sync bundle (supplier mapping)
 * 3. DINAMIC default
 */
export class LocalLabelProfileResolver {
  private cache = new Map<string, { item: ResolvedLocalLabelProfile; position: ResolvedLocalLabelProfile }>();

  constructor(private readonly repo: OfflineRecognitionConfigRepository) {}

  invalidate(): void {
    this.cache.clear();
  }

  async resolveForAisle(
    inventoryId: string,
    aisleId: string,
  ): Promise<{ item: ResolvedLocalLabelProfile; position: ResolvedLocalLabelProfile }> {
    const key = `${inventoryId}:${aisleId}`;
    const hit = this.cache.get(key);
    if (hit) return hit;

    const aisle = await this.repo.getAisleConfig(inventoryId, aisleId);
    const item = await this.resolveOne({
      inventoryId,
      labelKind: 'ITEM',
      override: aisle?.item_profile_source_override ?? null,
      effective: aisle?.effective_item_source ?? 'DINAMIC',
      clientSupplierId: aisle?.client_supplier_id ?? null,
    });
    const position = await this.resolveOne({
      inventoryId,
      labelKind: 'POSITION',
      override: aisle?.position_profile_source_override ?? null,
      effective: aisle?.effective_position_source ?? 'DINAMIC',
      clientSupplierId: aisle?.client_supplier_id ?? null,
    });
    const resolved = { item, position };
    this.cache.set(key, resolved);
    return resolved;
  }

  private async resolveOne(input: {
    inventoryId: string;
    labelKind: 'ITEM' | 'POSITION';
    override: string | null;
    effective: string;
    clientSupplierId: string | null;
  }): Promise<ResolvedLocalLabelProfile> {
    let source: ResolvedLocalProfileSource = 'DINAMIC';
    let resolutionSource: ResolvedLocalLabelProfile['resolutionSource'] = 'DEFAULT';
    const override = (input.override || '').toUpperCase();
    if (override === 'DINAMIC' || override === 'SUPPLIER') {
      source = override;
      resolutionSource = 'AISLE_OVERRIDE';
    } else {
      const eff = (input.effective || 'DINAMIC').toUpperCase();
      if (eff === 'SUPPLIER') {
        source = 'SUPPLIER';
        resolutionSource = 'CLIENT_SUPPLIER';
      }
    }

    if (source !== 'SUPPLIER') {
      return {
        labelKind: input.labelKind,
        source: 'DINAMIC',
        resolutionSource,
        clientSupplierId: input.clientSupplierId,
        profile: null,
        configuration: null,
        missingSupplierProfile: false,
      };
    }

    if (!input.clientSupplierId) {
      return {
        labelKind: input.labelKind,
        source: 'SUPPLIER',
        resolutionSource,
        clientSupplierId: null,
        profile: null,
        configuration: null,
        missingSupplierProfile: true,
      };
    }

    const profile = await this.repo.getProfile(
      input.inventoryId,
      input.clientSupplierId,
      input.labelKind,
    );
    if (!profile) {
      return {
        labelKind: input.labelKind,
        source: 'SUPPLIER',
        resolutionSource,
        clientSupplierId: input.clientSupplierId,
        profile: null,
        configuration: null,
        missingSupplierProfile: true,
      };
    }

    let configuration: OfflineExtractionConfiguration | null = null;
    try {
      configuration = JSON.parse(profile.configuration_json) as OfflineExtractionConfiguration;
    } catch {
      configuration = null;
    }

    return {
      labelKind: input.labelKind,
      source: 'SUPPLIER',
      resolutionSource,
      clientSupplierId: input.clientSupplierId,
      profile,
      configuration,
      missingSupplierProfile: configuration == null,
    };
  }
}
