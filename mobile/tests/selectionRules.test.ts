import { evaluateAisleSelection } from '../src/core/aisleSelection';
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

function validAisle(overrides: Record<string, unknown> = {}): AisleDto {
  return normalizeAisleDto({
    id: 'aisle-1',
    inventory_id: 'inv-1',
    code: 'A1',
    status: 'created',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    is_active: true,
    assets_count: 0,
    positions_count: 0,
    pending_review_positions_count: 0,
    ...overrides,
  });
}

describe('selection rules', () => {
  it.each([
    'draft',
    'failed',
    'processing',
    'in_review',
    'completed',
    'unknown',
    '',
  ])('always allows inventory selection for status %s', (status) => {
    expect(canSelectInventory(inventory(status))).toEqual({ ok: true, reason: null });
  });

  it.each([
    { is_active: true },
    { is_active: false },
    { is_active: null },
    { is_active: undefined },
    { status: 'processing' },
    { status: 'queued' },
    { status: 'inactive' },
    { status: 'completed' },
    { latest_job: { id: 'j', status: 'running', created_at: '', updated_at: '' } },
    { latest_job: { id: 'j', status: 'processing', created_at: '', updated_at: '' } },
    { latest_job: { id: 'j', status: 'completed', created_at: '', updated_at: '' } },
    { latest_job: { id: 'j', status: 'failed', created_at: '', updated_at: '' } },
  ])('always allows aisle selection %#', (overrides) => {
    expect(evaluateAisleSelection(validAisle(overrides))).toEqual({
      selectable: true,
      reason: null,
    });
    expect(canSelectAisle(validAisle(overrides)).ok).toBe(true);
  });

  it('never blocks for local exclusive capture hints', () => {
    expect(
      evaluateAisleSelection(validAisle(), {
        exclusiveCaptureOnOtherAisle: true,
        exclusiveCaptureOpen: true,
      }),
    ).toEqual({ selectable: true, reason: null });
  });
});
