import { canSelectAisle } from '../src/features/aisles/aisleService';
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

const aisle = (status: string, isActive = true): AisleDto => ({
  id: 'aisle-1',
  inventory_id: 'inv-1',
  code: 'A1',
  status,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_active: isActive,
  assets_count: 0,
  positions_count: 0,
  pending_review_positions_count: 0,
});

describe('selection rules', () => {
  it('allows only conservative inventory states for capture', () => {
    expect(canSelectInventory(inventory('draft')).ok).toBe(true);
    expect(canSelectInventory(inventory('failed')).ok).toBe(true);
    expect(canSelectInventory(inventory('processing')).ok).toBe(false);
    expect(canSelectInventory(inventory('completed')).ok).toBe(false);
    expect(canSelectInventory(inventory('unknown')).ok).toBe(false);
  });

  it('allows only active aisles in capture-ready states', () => {
    expect(canSelectAisle(aisle('created')).ok).toBe(true);
    expect(canSelectAisle(aisle('assets_uploaded')).ok).toBe(true);
    expect(canSelectAisle(aisle('created', false)).ok).toBe(false);
    expect(canSelectAisle(aisle('processing')).ok).toBe(false);
    expect(canSelectAisle(aisle('unknown')).ok).toBe(false);
  });
});

