import type { LocalCatalogRepository } from '../../database/repositories/localCatalogRepository';
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
  readonly recognitionConfigNotReady: boolean;
}

export interface AisleProfileResolutionContext {
  readonly inventoryId: string;
  readonly aisleId: string;
  readonly clientSupplierId?: string | null;
  readonly itemProfileSourceOverride?: string | null;
  readonly positionProfileSourceOverride?: string | null;
  readonly effectiveItemSource?: string | null;
  readonly effectivePositionSource?: string | null;
  readonly supplierConfigNotReady?: boolean;
}

/**
 * Precedence matches backend LabelProfileResolver:
 * 1. aisle override
 * 2. effective source from sync bundle (supplier mapping)
 * 3. DINAMIC default
 */
export class LocalLabelProfileResolver {
  private cache = new Map<string, { item: ResolvedLocalLabelProfile; position: ResolvedLocalLabelProfile }>();

  constructor(
    private readonly repo: OfflineRecognitionConfigRepository,
    private readonly catalog?: LocalCatalogRepository,
  ) {}

  invalidate(): void {
    this.cache.clear();
  }

  async resolveForAisle(
    inventoryId: string,
    aisleId: string,
  ): Promise<{ item: ResolvedLocalLabelProfile; position: ResolvedLocalLabelProfile }> {
    const context = await this.buildContext(inventoryId, aisleId);
    return this.resolveFromContext(context);
  }

  async resolveFromContext(
    context: AisleProfileResolutionContext,
  ): Promise<{ item: ResolvedLocalLabelProfile; position: ResolvedLocalLabelProfile }> {
    const key = `${context.inventoryId}:${context.aisleId}`;
    const hit = this.cache.get(key);
    if (hit) return hit;

    const item = await this.resolveOne({
      inventoryId: context.inventoryId,
      labelKind: 'ITEM',
      override: context.itemProfileSourceOverride ?? null,
      effective: context.effectiveItemSource ?? 'DINAMIC',
      clientSupplierId: context.clientSupplierId ?? null,
      supplierConfigNotReady: context.supplierConfigNotReady === true,
    });
    const position = await this.resolveOne({
      inventoryId: context.inventoryId,
      labelKind: 'POSITION',
      override: context.positionProfileSourceOverride ?? null,
      effective: context.effectivePositionSource ?? 'DINAMIC',
      clientSupplierId: context.clientSupplierId ?? null,
      supplierConfigNotReady: context.supplierConfigNotReady === true,
    });
    const resolved = { item, position };
    this.cache.set(key, resolved);
    return resolved;
  }

  private async buildContext(
    inventoryId: string,
    aisleId: string,
  ): Promise<AisleProfileResolutionContext> {
    const aisleConfig = await this.repo.getAisleConfig(inventoryId, aisleId);
    if (aisleConfig) {
      return {
        inventoryId,
        aisleId,
        clientSupplierId: aisleConfig.client_supplier_id,
        itemProfileSourceOverride: aisleConfig.item_profile_source_override,
        positionProfileSourceOverride: aisleConfig.position_profile_source_override,
        effectiveItemSource: aisleConfig.effective_item_source,
        effectivePositionSource: aisleConfig.effective_position_source,
      };
    }

    const localAisle = await this.catalog?.getAisleById(inventoryId, aisleId);
    // A freshly-created remote aisle can predate the next recognition bundle.
    // Its explicit catalog association is authoritative enough to apply the
    // ClientSupplier base sources until an aisle mapping (and its overrides)
    // arrives. Existing aisle mappings still win above.
    if (localAisle?.client_supplier_id) {
      const supplierId = localAisle.client_supplier_id;
      const baseSources = await this.repo.getSupplierBaseSources(inventoryId, supplierId);
      if (!baseSources) {
        return {
          inventoryId,
          aisleId,
          clientSupplierId: supplierId,
          itemProfileSourceOverride: null,
          positionProfileSourceOverride: null,
          effectiveItemSource: 'DINAMIC',
          effectivePositionSource: 'DINAMIC',
          supplierConfigNotReady: true,
        };
      }
      return {
        inventoryId,
        aisleId,
        clientSupplierId: supplierId,
        itemProfileSourceOverride: null,
        positionProfileSourceOverride: null,
        effectiveItemSource: baseSources.item_source,
        effectivePositionSource: baseSources.position_source,
      };
    }

    return {
      inventoryId,
      aisleId,
      clientSupplierId: null,
      itemProfileSourceOverride: null,
      positionProfileSourceOverride: null,
      effectiveItemSource: 'DINAMIC',
      effectivePositionSource: 'DINAMIC',
    };
  }

  private async resolveOne(input: {
    inventoryId: string;
    labelKind: 'ITEM' | 'POSITION';
    override: string | null;
    effective: string;
    clientSupplierId: string | null;
    supplierConfigNotReady?: boolean;
  }): Promise<ResolvedLocalLabelProfile> {
    if (input.supplierConfigNotReady) {
      return {
        labelKind: input.labelKind,
        source: 'DINAMIC',
        resolutionSource: 'DEFAULT',
        clientSupplierId: input.clientSupplierId,
        profile: null,
        configuration: null,
        missingSupplierProfile: true,
        recognitionConfigNotReady: true,
      };
    }

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
        recognitionConfigNotReady: false,
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
        recognitionConfigNotReady: false,
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
        recognitionConfigNotReady: false,
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
      recognitionConfigNotReady: false,
    };
  }
}
