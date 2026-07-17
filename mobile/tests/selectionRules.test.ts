import {
  evaluateAisleSelection,
  normalizeIsActive,
  aisleBlockReasonLabel,
} from '../src/core/aisleSelection';
import { canSelectAisle, normalizeAisleDto } from '../src/features/aisles/aisleService';
import { canSelectInventory } from '../src/features/inventories/inventoryService';
import type { AisleDto, InventoryListItemDto } from '../src/services/api/types';

const inventory = (status: string): InventoryListItemDto => ({
  id: 'inv-1',
  name: 'Inventario',
  status,
  client_id: null,
  created_at: null,
  updated_at: null,
  aisles_count: 1,
  pending_review_count: 0,
  last_activity_at: null,
  processing_mode: 'production',
});

const aisle = (overrides: Partial<AisleDto> & { status: string }): AisleDto => ({
  id: 'aisle-1',
  inventory_id: 'inv-1',
  code: 'A1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_active: true,
  assets_count: 0,
  positions_count: 0,
  pending_review_positions_count: 0,
  ...overrides,
});

describe('selection rules', () => {
  it('allows only conservative inventory states for capture', () => {
    expect(canSelectInventory(inventory('draft')).ok).toBe(true);
    expect(canSelectInventory(inventory('failed')).ok).toBe(true);
    expect(canSelectInventory(inventory('processing')).ok).toBe(false);
    expect(canSelectInventory(inventory('completed')).ok).toBe(false);
    expect(canSelectInventory(inventory('unknown')).ok).toBe(false);
  });

  it('allows active aisles including completed prior work and existing photos', () => {
    expect(evaluateAisleSelection(aisle({ status: 'created' })).selectable).toBe(true);
    expect(evaluateAisleSelection(aisle({ status: 'assets_uploaded', assets_count: 12 })).selectable).toBe(
      true,
    );
    expect(evaluateAisleSelection(aisle({ status: 'completed' })).selectable).toBe(true);
    expect(evaluateAisleSelection(aisle({ status: 'processed' })).selectable).toBe(true);
    expect(evaluateAisleSelection(aisle({ status: 'failed' })).selectable).toBe(true);
    expect(
      evaluateAisleSelection(
        aisle({
          status: 'completed',
          latest_job: {
            id: 'j1',
            status: 'success',
            created_at: '',
            updated_at: '',
          },
        }),
      ).selectable,
    ).toBe(true);
  });

  it('treats missing / null is_active as active', () => {
    expect(normalizeIsActive(undefined)).toBe(true);
    expect(normalizeIsActive(null)).toBe(true);
    expect(evaluateAisleSelection({ id: 'a', status: 'created' }).selectable).toBe(true);
    expect(evaluateAisleSelection({ id: 'a', status: 'created', is_active: null }).selectable).toBe(true);
    expect(canSelectAisle(normalizeAisleDto({ id: 'a', status: 'created' })).ok).toBe(true);
  });

  it('blocks inactive aisles', () => {
    expect(evaluateAisleSelection(aisle({ status: 'created', is_active: false })).reason).toBe('inactive');
    expect(aisleBlockReasonLabel('inactive')).toMatch(/inactivo/i);
  });

  it('blocks processing aisle / job states with normalization', () => {
    expect(evaluateAisleSelection(aisle({ status: 'processing' })).reason).toBe('processing');
    expect(evaluateAisleSelection(aisle({ status: 'PROCESSING' })).reason).toBe('processing');
    expect(evaluateAisleSelection(aisle({ status: '  Queued ' })).reason).toBe('processing');
    expect(
      evaluateAisleSelection(
        aisle({
          status: 'assets_uploaded',
          latest_job: { id: 'j', status: 'running', created_at: '', updated_at: '' },
        }),
      ).reason,
    ).toBe('processing');
  });

  it('blocks when another aisle has exclusive local capture', () => {
    expect(
      evaluateAisleSelection(aisle({ status: 'created' }), { exclusiveCaptureOnOtherAisle: true }).reason,
    ).toBe('capture_in_progress');
  });

  it('allows continuing the same aisle with open local capture', () => {
    expect(
      evaluateAisleSelection(aisle({ status: 'created' }), { exclusiveCaptureOpen: true }).selectable,
    ).toBe(true);
  });

  it('rejects invalid payloads', () => {
    expect(evaluateAisleSelection(null).reason).toBe('invalid_data');
    expect(evaluateAisleSelection({ status: 'created' }).reason).toBe('invalid_data');
  });
});
