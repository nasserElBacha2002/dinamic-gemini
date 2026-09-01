import { AisleService } from '../src/features/aisles/aisleService';
import { LocalAisleError } from '../src/features/aisles/localAisleErrors';
import { LocalLabelProfileResolver } from '../src/features/offlineRecognition/localLabelProfileResolver';
import { LocalCatalogRepository } from '../src/database/repositories/localCatalogRepository';
import type { CatalogSnapshot } from '../src/database/repositories/localCatalogRepository';
import { validateSupplierPayloadOffline } from '../src/core/offlineSupplierLabelValidator';

const INVENTORY = {
  id: 'inv-1',
  client_id: 'client-1',
  name: 'Inv',
  status: 'active',
  active: 1,
  processing_mode: 'production',
  aisles_count: 1,
  pending_review_count: 0,
  last_activity_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  server_updated_at: null,
  synced_at: '2026-01-01T00:00:00Z',
};

const SUPPLIER = {
  id: 'sup-b',
  client_id: 'client-1',
  name: 'pruebas b',
  status: 'active',
  active: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  server_updated_at: null,
  synced_at: '2026-01-01T00:00:00Z',
};

function segmentedItemConfig() {
  return {
    recognition_mode: 'FULL',
    required_fields: ['label_id', 'sku', 'quantity'],
    deterministic: {
      payload_structure: 'SEGMENTED',
      delimiter: '|',
      expected_segment_count: 3,
      character_set: 'ANY',
      normalization: {
        trim_outer_whitespace: true,
        case_normalization: 'NONE',
        remove_internal_spaces: false,
        remove_hyphens: false,
      },
      field_mappings: [
        { target: 'label_id', source: 'SEGMENT', segment_index: 0 },
        { target: 'sku', source: 'SEGMENT', segment_index: 1 },
        { target: 'quantity', source: 'SEGMENT', segment_index: 2 },
      ],
    },
  };
}

function segmentedPositionConfig() {
  return {
    recognition_mode: 'FULL',
    required_fields: ['position_id', 'pallet', 'side', 'level'],
    deterministic: {
      payload_structure: 'SEGMENTED',
      delimiter: '|',
      expected_segment_count: 4,
      character_set: 'ANY',
      normalization: {
        trim_outer_whitespace: true,
        case_normalization: 'UPPER',
        remove_internal_spaces: false,
        remove_hyphens: false,
      },
      field_mappings: [
        { target: 'position_id', source: 'SEGMENT', segment_index: 0 },
        { target: 'pallet', source: 'SEGMENT', segment_index: 1 },
        { target: 'side', source: 'SEGMENT', segment_index: 2 },
        { target: 'level', source: 'SEGMENT', segment_index: 3 },
      ],
    },
  };
}

describe('Phase 3 LOCAL_ONLY aisles', () => {
  it('createLocal offline does not call API and persists aisle', async () => {
    const api = { post: jest.fn(), get: jest.fn() };
    let inserted: unknown = null;
    const catalog = {
      getInventoryById: jest.fn(async () => INVENTORY),
      getSupplierById: jest.fn(async () => SUPPLIER),
      insertLocalAisle: jest.fn(async (input) => {
        inserted = input;
        return {
          ...input,
          inventory_id: input.inventoryId,
          code: input.code,
          status: 'created',
          active: 1,
          assets_count: 0,
          positions_count: 0,
          pending_review_positions_count: 0,
          origin: 'LOCAL',
          sync_status: 'LOCAL_ONLY',
          created_offline_at: input.createdAtIso,
          created_at: input.createdAtIso,
          updated_at: input.createdAtIso,
          server_updated_at: null,
          synced_at: input.createdAtIso,
          client_supplier_id: input.clientSupplierId,
        };
      }),
    };
    const recognitionRepo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: '2026-01-01T00:00:00Z',
        generated_at: null,
      })),
      getSupplierBaseSources: jest.fn(async () => ({
        item_source: 'SUPPLIER',
        position_source: 'SUPPLIER',
      })),
      getProfile: jest.fn(async (_inv, _sup, kind) => ({
        inventory_id: 'inv-1',
        client_supplier_id: 'sup-b',
        label_kind: kind,
        source: 'SUPPLIER',
        profile_id: kind === 'ITEM' ? 'prof-item' : 'prof-pos',
        profile_version: kind === 'ITEM' ? 10 : 3,
        configuration_schema_version: 2,
        recognition_mode: 'MINIMAL',
        semantic_type: null,
        configuration_json: JSON.stringify(
          kind === 'ITEM' ? segmentedItemConfig() : segmentedPositionConfig(),
        ),
        synced_at: '2026-01-01T00:00:00Z',
      })),
    };

    const service = new AisleService(
      api as never,
      undefined,
      catalog as never,
      undefined,
      { getState: () => 'offline' } as never,
      recognitionRepo as never,
    );

    const aisle = await service.createLocal({
      inventoryId: 'inv-1',
      code: 'Pasillo Offline 01',
      clientSupplierId: 'sup-b',
    });

    expect(api.post).not.toHaveBeenCalled();
    expect(catalog.insertLocalAisle).toHaveBeenCalledTimes(1);
    expect(inserted).toMatchObject({
      inventoryId: 'inv-1',
      code: 'Pasillo Offline 01',
      clientSupplierId: 'sup-b',
    });
    expect(aisle.sync_status).toBe('LOCAL_ONLY');
    expect(aisle.origin).toBe('LOCAL');
    expect(aisle.id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it('rejects supplier client mismatch', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => INVENTORY),
      getSupplierById: jest.fn(async () => ({ ...SUPPLIER, client_id: 'other-client' })),
      insertLocalAisle: jest.fn(),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
      undefined,
      { getState: () => 'offline' } as never,
      {} as never,
    );
    await expect(
      service.createLocal({
        inventoryId: 'inv-1',
        code: 'A1',
        clientSupplierId: 'sup-b',
      }),
    ).rejects.toMatchObject({ code: 'SUPPLIER_CLIENT_MISMATCH' });
    expect(catalog.insertLocalAisle).not.toHaveBeenCalled();
  });

  it('rejects supplier when inventory client is null', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => ({ ...INVENTORY, client_id: null })),
      insertLocalAisle: jest.fn(),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
      undefined,
      { getState: () => 'offline' } as never,
      {} as never,
    );
    await expect(
      service.createLocal({
        inventoryId: 'inv-1',
        code: 'A1',
        clientSupplierId: 'sup-b',
      }),
    ).rejects.toMatchObject({ code: 'INVENTORY_CLIENT_NOT_AVAILABLE_OFFLINE' });
    expect(catalog.insertLocalAisle).not.toHaveBeenCalled();
  });

  it('rejects inactive inventory', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => ({ ...INVENTORY, active: 0 })),
      insertLocalAisle: jest.fn(),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
    );
    await expect(
      service.createLocal({ inventoryId: 'inv-1', code: 'A1', clientSupplierId: 'sup-b' }),
    ).rejects.toMatchObject({ code: 'INVENTORY_INACTIVE' });
  });

  it('rejects inactive supplier', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => INVENTORY),
      getSupplierById: jest.fn(async () => ({ ...SUPPLIER, active: 0 })),
      insertLocalAisle: jest.fn(),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
      undefined,
      undefined,
      {} as never,
    );
    await expect(
      service.createLocal({ inventoryId: 'inv-1', code: 'A1', clientSupplierId: 'sup-b' }),
    ).rejects.toMatchObject({ code: 'SUPPLIER_INACTIVE' });
  });

  it('rejects when recognition profiles missing', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => INVENTORY),
      getSupplierById: jest.fn(async () => SUPPLIER),
      insertLocalAisle: jest.fn(),
    };
    const recognitionRepo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: '2026-01-01T00:00:00Z',
        generated_at: null,
      })),
      getSupplierBaseSources: jest.fn(async () => ({
        item_source: 'SUPPLIER',
        position_source: 'SUPPLIER',
      })),
      getProfile: jest.fn(async () => null),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
      undefined,
      undefined,
      recognitionRepo as never,
    );
    await expect(
      service.createLocal({ inventoryId: 'inv-1', code: 'A1', clientSupplierId: 'sup-b' }),
    ).rejects.toMatchObject({ code: 'RECOGNITION_CONFIG_NOT_READY' });
  });

  it('double submit creates only one aisle when in-flight', async () => {
    const catalog = {
      getInventoryById: jest.fn(async () => INVENTORY),
      getSupplierById: jest.fn(async () => SUPPLIER),
      insertLocalAisle: jest.fn(
        () =>
          new Promise((resolve) => {
            setTimeout(
              () =>
                resolve({
                  id: 'aisle-1',
                  inventory_id: 'inv-1',
                  code: 'A1',
                  status: 'created',
                  active: 1,
                  assets_count: 0,
                  positions_count: 0,
                  pending_review_positions_count: 0,
                  origin: 'LOCAL',
                  sync_status: 'LOCAL_ONLY',
                  client_supplier_id: 'sup-b',
                  created_offline_at: '2026-01-01T00:00:00Z',
                  created_at: '2026-01-01T00:00:00Z',
                  updated_at: '2026-01-01T00:00:00Z',
                  server_updated_at: null,
                  synced_at: '2026-01-01T00:00:00Z',
                }),
              20,
            );
          }),
      ),
    };
    const recognitionRepo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: '2026-01-01T00:00:00Z',
        generated_at: null,
      })),
      getSupplierBaseSources: jest.fn(async () => ({
        item_source: 'SUPPLIER',
        position_source: 'SUPPLIER',
      })),
      getProfile: jest.fn(async (_i, _s, kind) => ({
        label_kind: kind,
        profile_id: 'p',
        profile_version: 1,
        configuration_json: JSON.stringify(
          kind === 'ITEM' ? segmentedItemConfig() : segmentedPositionConfig(),
        ),
      })),
    };
    const service = new AisleService(
      { post: jest.fn() } as never,
      undefined,
      catalog as never,
      undefined,
      undefined,
      recognitionRepo as never,
    );
    const p1 = service.createLocal({ inventoryId: 'inv-1', code: 'A1', clientSupplierId: 'sup-b' });
    await expect(
      service.createLocal({ inventoryId: 'inv-1', code: 'A1', clientSupplierId: 'sup-b' }),
    ).rejects.toBeInstanceOf(LocalAisleError);
    await p1;
    expect(catalog.insertLocalAisle).toHaveBeenCalledTimes(1);
  });

  it('resolves profiles for LOCAL aisle without remote aisle config row', async () => {
    const recognitionRepo = {
      getAisleConfig: jest.fn(async () => null),
      getSupplierBaseSources: jest.fn(async () => ({
        item_source: 'SUPPLIER',
        position_source: 'SUPPLIER',
      })),
      getProfile: jest.fn(async (_i, _s, kind) => ({
        inventory_id: 'inv-1',
        client_supplier_id: 'sup-b',
        label_kind: kind,
        source: 'SUPPLIER',
        profile_id: kind === 'ITEM' ? 'prof-item' : 'prof-pos',
        profile_version: kind === 'ITEM' ? 10 : 3,
        configuration_schema_version: 2,
        recognition_mode: 'MINIMAL',
        semantic_type: null,
        configuration_json: JSON.stringify(
          kind === 'ITEM' ? segmentedItemConfig() : segmentedPositionConfig(),
        ),
        synced_at: '2026-01-01T00:00:00Z',
      })),
    };
    const catalog = {
      getAisleById: jest.fn(async () => ({
        id: 'local-aisle-1',
        inventory_id: 'inv-1',
        code: 'Local',
        status: 'created',
        active: 1,
        client_supplier_id: 'sup-b',
        origin: 'LOCAL',
        sync_status: 'LOCAL_ONLY',
      })),
    };
    const resolver = new LocalLabelProfileResolver(
      recognitionRepo as never,
      catalog as never,
    );
    const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle-1');
    expect(resolved.item.profile?.profile_version).toBe(10);
    expect(resolved.position.profile?.profile_version).toBe(3);
    expect(resolved.item.missingSupplierProfile).toBe(false);
    expect(recognitionRepo.getAisleConfig).toHaveBeenCalled();
  });

  it('parses golden ITEM payload for supplier profiles used by local aisles', () => {
    const result = validateSupplierPayloadOffline({
      rawPayload: 'LPNA000184|SKU773421|24',
      labelKind: 'ITEM',
      configuration: segmentedItemConfig(),
      profileId: 'prof-item',
      profileVersion: 10,
    });
    expect(result.status).toBe('VALID');
    expect(result.labelId).toBe('LPNA000184');
    expect(result.sku).toBe('SKU773421');
    expect(result.quantity).toBe(24);
  });

  it('parses golden POSITION payload for supplier profiles used by local aisles', () => {
    const result = validateSupplierPayloadOffline({
      rawPayload: 'A04-R-02|04|RIGHT|02',
      labelKind: 'POSITION',
      configuration: segmentedPositionConfig(),
      profileId: 'prof-pos',
      profileVersion: 3,
    });
    expect(result.status).toBe('VALID');
    expect(result.positionId).toBe('A04-R-02');
    expect(result.pallet).toBe('04');
    expect(result.side).toBe('RIGHT');
    expect(result.level).toBe('02');
    expect(result.quantity).toBeNull();
  });

  it('replaceCatalogSnapshot preserves LOCAL_ONLY aisles', async () => {
    const runs: string[] = [];
    const db = {
      withTransactionAsync: jest.fn(async (fn: () => Promise<void>) => fn()),
      runAsync: jest.fn(async (sql: string) => {
        runs.push(sql);
      }),
    };
    const repo = new LocalCatalogRepository(db as never);
    const snapshot: CatalogSnapshot = {
      revision: 'rev-2',
      inventories: [
        {
          id: 'inv-1',
          name: 'Inv',
          status: 'active',
          client_id: 'client-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          aisles_count: 1,
          pending_review_count: 0,
          last_activity_at: null,
          processing_mode: 'production',
        },
      ],
      suppliers: [],
      aisles: [
        {
          id: 'remote-1',
          inventory_id: 'inv-1',
          code: 'Remote',
          status: 'created',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          assets_count: 0,
          positions_count: 0,
          pending_review_positions_count: 0,
        },
      ],
    };
    await repo.replaceCatalogSnapshot(snapshot, '2026-02-01T00:00:00Z');
    expect(runs.some((s) => s.includes("origin IS NULL OR origin = 'REMOTE'"))).toBe(true);
    expect(runs.some((s) => s.includes("'REMOTE', 'REMOTE_SYNCED'"))).toBe(true);
  });

  describe('LOCAL aisle ClientSupplier base source resolution', () => {
    function buildResolver(input: {
      itemSource: 'DINAMIC' | 'SUPPLIER';
      positionSource: 'DINAMIC' | 'SUPPLIER';
      remoteAisles?: Array<{
        aisle_id: string;
        effective_item_source: 'DINAMIC' | 'SUPPLIER';
        effective_position_source?: 'DINAMIC' | 'SUPPLIER';
        item_profile_source_override?: 'DINAMIC' | 'SUPPLIER' | null;
      }>;
      profiles?: Partial<Record<'ITEM' | 'POSITION', boolean>>;
    }) {
      const remoteAisles = input.remoteAisles ?? [];
      const recognitionRepo = {
        getAisleConfig: jest.fn(async (_inv: string, aisleId: string) => {
          const row = remoteAisles.find((a) => a.aisle_id === aisleId);
          if (!row) return null;
          return {
            inventory_id: 'inv-1',
            aisle_id: row.aisle_id,
            client_supplier_id: 'sup-b',
            item_profile_source_override: row.item_profile_source_override ?? null,
            position_profile_source_override: null,
            effective_item_source: row.effective_item_source,
            effective_position_source: row.effective_position_source ?? 'DINAMIC',
            synced_at: '2026-01-01T00:00:00Z',
          };
        }),
        getSupplierBaseSources: jest.fn(async () => ({
          item_source: input.itemSource,
          position_source: input.positionSource,
        })),
        getProfile: jest.fn(async (_i, _s, kind: 'ITEM' | 'POSITION') => {
          if (input.profiles?.[kind] === false) return null;
          return {
            inventory_id: 'inv-1',
            client_supplier_id: 'sup-b',
            label_kind: kind,
            source: 'SUPPLIER',
            profile_id: kind === 'ITEM' ? 'prof-item' : 'prof-pos',
            profile_version: kind === 'ITEM' ? 10 : 3,
            configuration_schema_version: 2,
            recognition_mode: 'MINIMAL',
            semantic_type: null,
            configuration_json: JSON.stringify(
              kind === 'ITEM' ? segmentedItemConfig() : segmentedPositionConfig(),
            ),
            synced_at: '2026-01-01T00:00:00Z',
          };
        }),
      };
      const catalog = {
        getAisleById: jest.fn(async (_inv: string, aisleId: string) => {
          if (aisleId === 'local-aisle') {
            return {
              id: 'local-aisle',
              inventory_id: 'inv-1',
              code: 'Local',
              status: 'created',
              active: 1,
              client_supplier_id: 'sup-b',
              origin: 'LOCAL',
              sync_status: 'LOCAL_ONLY',
            };
          }
          return {
            id: aisleId,
            inventory_id: 'inv-1',
            code: aisleId,
            status: 'created',
            active: 1,
            client_supplier_id: 'sup-b',
            origin: 'REMOTE',
            sync_status: 'REMOTE_SYNCED',
          };
        }),
      };
      return {
        resolver: new LocalLabelProfileResolver(recognitionRepo as never, catalog as never),
        recognitionRepo,
      };
    }

    it('uses ClientSupplier ITEM SUPPLIER when remote aisle overrides ITEM to DINAMIC', async () => {
      const { resolver } = buildResolver({
        itemSource: 'SUPPLIER',
        positionSource: 'SUPPLIER',
        remoteAisles: [
          {
            aisle_id: 'remote-a',
            effective_item_source: 'DINAMIC',
            item_profile_source_override: 'DINAMIC',
          },
        ],
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.source).toBe('SUPPLIER');
      expect(resolved.item.resolutionSource).toBe('CLIENT_SUPPLIER');
      expect(resolved.item.profile?.profile_id).toBe('prof-item');
    });

    it('uses ClientSupplier ITEM DINAMIC when remote aisle overrides ITEM to SUPPLIER', async () => {
      const { resolver } = buildResolver({
        itemSource: 'DINAMIC',
        positionSource: 'DINAMIC',
        remoteAisles: [
          {
            aisle_id: 'remote-a',
            effective_item_source: 'SUPPLIER',
            item_profile_source_override: 'SUPPLIER',
          },
        ],
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.source).toBe('DINAMIC');
      expect(resolved.item.profile).toBeNull();
    });

    it('does not depend on remote aisle SQL row order for local aisle', async () => {
      const { resolver, recognitionRepo } = buildResolver({
        itemSource: 'SUPPLIER',
        positionSource: 'SUPPLIER',
        remoteAisles: [
          { aisle_id: 'remote-a', effective_item_source: 'DINAMIC', item_profile_source_override: 'DINAMIC' },
          { aisle_id: 'remote-b', effective_item_source: 'SUPPLIER', item_profile_source_override: 'SUPPLIER' },
        ],
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.source).toBe('SUPPLIER');
      expect(recognitionRepo.getSupplierBaseSources).toHaveBeenCalledWith('inv-1', 'sup-b');
      expect(recognitionRepo.getAisleConfig).toHaveBeenCalledWith('inv-1', 'local-aisle');
    });

    it('uses DINAMIC when ClientSupplier source is DINAMIC even if profile exists', async () => {
      const { resolver } = buildResolver({
        itemSource: 'DINAMIC',
        positionSource: 'DINAMIC',
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.source).toBe('DINAMIC');
      expect(resolved.item.profile).toBeNull();
      expect(resolved.position.source).toBe('DINAMIC');
    });

    it('fails closed when ClientSupplier source is SUPPLIER but profile missing', async () => {
      const { resolver } = buildResolver({
        itemSource: 'SUPPLIER',
        positionSource: 'SUPPLIER',
        profiles: { ITEM: false, POSITION: true },
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.missingSupplierProfile).toBe(true);
      expect(resolved.position.missingSupplierProfile).toBe(false);
    });

    it('resolves mixed ITEM SUPPLIER and POSITION DINAMIC independently', async () => {
      const { resolver } = buildResolver({
        itemSource: 'SUPPLIER',
        positionSource: 'DINAMIC',
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'local-aisle');
      expect(resolved.item.source).toBe('SUPPLIER');
      expect(resolved.item.profile?.profile_id).toBe('prof-item');
      expect(resolved.position.source).toBe('DINAMIC');
      expect(resolved.position.profile).toBeNull();
    });

    it('remote aisle still uses aisle effective override chain', async () => {
      const { resolver } = buildResolver({
        itemSource: 'SUPPLIER',
        positionSource: 'SUPPLIER',
        remoteAisles: [
          {
            aisle_id: 'remote-a',
            effective_item_source: 'DINAMIC',
            item_profile_source_override: 'DINAMIC',
          },
        ],
      });
      const resolved = await resolver.resolveForAisle('inv-1', 'remote-a');
      expect(resolved.item.source).toBe('DINAMIC');
      expect(resolved.item.resolutionSource).toBe('AISLE_OVERRIDE');
    });
  });
});
