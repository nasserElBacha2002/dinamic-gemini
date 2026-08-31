import { OfflineRecognitionConfigRepository } from '../src/database/repositories/offlineRecognitionConfigRepository';
import type { OfflineRecognitionBundleDto } from '../src/features/offlineRecognition/types';
import { OfflineRecognitionSyncService } from '../src/features/offlineRecognition/offlineRecognitionSyncService';
import { LocalLabelProfileResolver } from '../src/features/offlineRecognition/localLabelProfileResolver';
import { checkOfflineRecognitionReadiness } from '../src/features/offlineRecognition/checkOfflineRecognitionReadiness';

function sampleBundle(overrides?: Partial<OfflineRecognitionBundleDto>): OfflineRecognitionBundleDto {
  return {
    bundle_schema_version: 1,
    inventory_id: 'inv-1',
    client_id: 'client-1',
    generated_at: '2026-08-31T18:00:00Z',
    bundle_revision: 'rev-1',
    aisles: [
      {
        aisle_id: 'aisle-1',
        client_supplier_id: 'sup-a',
        item_profile_source_override: null,
        position_profile_source_override: null,
        effective_item_source: 'SUPPLIER',
        effective_position_source: 'SUPPLIER',
      },
    ],
    profiles: [
      {
        client_supplier_id: 'sup-a',
        label_kind: 'ITEM',
        source: 'SUPPLIER',
        profile_id: 'prof-item',
        profile_version: 3,
        configuration_schema_version: 2,
        recognition_mode: 'MINIMAL',
        semantic_type: 'LPN',
        configuration: {
          recognition_mode: 'MINIMAL',
          required_fields: ['label_id'],
          deterministic: {
            expected_prefix: 'LPNA',
            exact_length: 10,
            character_set: 'UPPERCASE_ALPHANUMERIC',
            payload_structure: 'SIMPLE',
            field_mappings: [{ target: 'label_id', source: 'WHOLE' }],
          },
        },
      },
      {
        client_supplier_id: 'sup-a',
        label_kind: 'POSITION',
        source: 'SUPPLIER',
        profile_id: 'prof-pos',
        profile_version: 3,
        configuration_schema_version: 2,
        recognition_mode: 'MINIMAL',
        configuration: {
          recognition_mode: 'MINIMAL',
          required_fields: ['position_id'],
          deterministic: {
            expected_prefix: 'A',
            exact_length: 8,
            character_set: 'ALPHANUMERIC_WITH_HYPHEN',
            payload_structure: 'SIMPLE',
            field_mappings: [{ target: 'position_id', source: 'WHOLE' }],
          },
        },
      },
    ],
    ...overrides,
  };
}

describe('offline recognition sync + readiness', () => {
  it('rejects incompatible bundle schema without writing', async () => {
    const replaceBundle = jest.fn();
    const repo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'old',
        synced_at: '2026-08-01T00:00:00Z',
        generated_at: null,
      })),
      replaceBundle,
    } as unknown as OfflineRecognitionConfigRepository;
    const api = {
      get: jest.fn(async () => sampleBundle({ bundle_schema_version: 99 })),
    };
    const sync = new OfflineRecognitionSyncService(api as never, repo);
    const result = await sync.syncInventory('inv-1');
    expect(result.ok).toBe(false);
    expect(result.errorCode).toBe('INCOMPATIBLE_BUNDLE_SCHEMA');
    expect(replaceBundle).not.toHaveBeenCalled();
  });

  it('skips replace when revision unchanged', async () => {
    const replaceBundle = jest.fn();
    const repo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: '2026-08-31T10:00:00Z',
        generated_at: null,
      })),
      replaceBundle,
    } as unknown as OfflineRecognitionConfigRepository;
    const api = {
      get: jest.fn(async () => sampleBundle({ bundle_revision: 'rev-1' })),
    };
    const sync = new OfflineRecognitionSyncService(api as never, repo);
    const result = await sync.syncInventory('inv-1');
    expect(result.ok).toBe(true);
    expect(result.skippedSameRevision).toBe(true);
    expect(replaceBundle).not.toHaveBeenCalled();
  });

  it('reports missing supplier profile for readiness', async () => {
    const repo = {
      getSyncMeta: jest.fn(async () => ({
        inventory_id: 'inv-1',
        client_id: 'client-1',
        bundle_schema_version: 1,
        bundle_revision: 'rev-1',
        synced_at: new Date().toISOString(),
        generated_at: null,
      })),
      getAisleConfig: jest.fn(async () => ({
        inventory_id: 'inv-1',
        aisle_id: 'aisle-1',
        client_supplier_id: 'sup-a',
        item_profile_source_override: null,
        position_profile_source_override: null,
        effective_item_source: 'SUPPLIER',
        effective_position_source: 'SUPPLIER',
        synced_at: new Date().toISOString(),
      })),
      getProfile: jest.fn(async () => null),
    } as unknown as OfflineRecognitionConfigRepository;
    const resolver = new LocalLabelProfileResolver(repo);
    const readiness = await checkOfflineRecognitionReadiness({
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      repo,
      resolver,
    });
    expect(readiness.status).toBe('MISSING_SUPPLIER_PROFILE');
  });
});
