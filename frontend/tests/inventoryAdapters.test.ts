import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import type { Aisle, Inventory } from '../src/api/types';
import {
  toAisleInventoryRowViewModel,
  toInventoryHeaderViewModel,
} from '../src/features/inventories/adapters';

function mockT(): TFunction {
  return ((key: string) => key) as unknown as TFunction;
}

describe('inventory view-model adapters', () => {
  it('toInventoryHeaderViewModel maps inventory DTO to header fields', () => {
    const inventory: Inventory = {
      id: 'inv-1',
      name: 'Warehouse A',
      status: 'draft',
      processing_mode: 'test',
      created_at: '2024-01-01T00:00:00Z',
    };
    const vm = toInventoryHeaderViewModel(inventory, mockT());
    expect(vm.title).toBe('Warehouse A');
    expect(vm.processingModeSemantic).toBe('warning');
    expect(vm.primaryConfigCaption).toBeNull();
  });

  it('toAisleInventoryRowViewModel flattens execution summary without leaking raw job in row shape', () => {
    const aisle = {
      id: 'a1',
      code: 'A-1',
      status: 'processed',
      assets_count: 2,
      positions_count: 5,
      pending_review_positions_count: 0,
      last_activity_at: '2024-01-02T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      latest_job: {
        id: 'job-1',
        status: 'succeeded',
        provider_name: 'gemini',
        model_name: 'm1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    } as unknown as Aisle;

    const row = toAisleInventoryRowViewModel(aisle, '—');
    expect(row.execution?.providerDisplay).toBe('gemini');
    expect(row.executionJobId).toBe('job-1');
    expect(row.processMenuAisle).toEqual({ id: 'a1', status: 'processed', assets_count: 2 });
  });
});
