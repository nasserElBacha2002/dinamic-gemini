import { describe, expect, it } from 'vitest';
import type { Aisle, SupplierReferenceImage } from '../src/api/types';
import { pickSupplierReferenceImagesForAisle } from '../src/features/inventories/adapters/aisleReferenceImages';

const cat: SupplierReferenceImage[] = [
  {
    id: 'a',
    client_supplier_id: 's1',
    filename: '1.png',
    mime_type: 'image/png',
    file_size: 1,
    created_at: 'x',
    updated_at: 'x',
  },
  {
    id: 'b',
    client_supplier_id: 's1',
    filename: '2.png',
    mime_type: 'image/png',
    file_size: 1,
    created_at: 'x',
    updated_at: 'x',
  },
  {
    id: 'c',
    client_supplier_id: 's1',
    filename: '3.png',
    mime_type: 'image/png',
    file_size: 1,
    created_at: 'x',
    updated_at: 'x',
  },
];

function aisleWithRefs(ids: string[]): Aisle {
  return {
    id: 'aisle-1',
    inventory_id: 'inv-1',
    code: '01',
    status: 'processed',
    created_at: 'x',
    updated_at: 'x',
    latest_job: {
      id: 'job-1',
      status: 'succeeded',
      created_at: 'x',
      updated_at: 'x',
      reference_usage: {
        resolved: true,
        resolved_count: ids.length,
        provider_consumed: true,
        provider_consumed_count: ids.length,
        reference_ids: ids,
        resolution_error: null,
      },
    },
  } as Aisle;
}

describe('pickSupplierReferenceImagesForAisle', () => {
  it('returns full catalog when no latest job reference_ids match', () => {
    const aisle = aisleWithRefs(['missing']);
    expect(pickSupplierReferenceImagesForAisle(aisle, cat).map((x) => x.id)).toEqual(['a', 'b', 'c']);
  });

  it('returns intersection when reference_ids match catalog', () => {
    const aisle = aisleWithRefs(['b', 'c']);
    expect(pickSupplierReferenceImagesForAisle(aisle, cat).map((x) => x.id)).toEqual(['b', 'c']);
  });

  it('returns empty when catalog empty', () => {
    const aisle = aisleWithRefs(['a']);
    expect(pickSupplierReferenceImagesForAisle(aisle, [])).toEqual([]);
    expect(pickSupplierReferenceImagesForAisle(aisle, undefined)).toEqual([]);
  });
});
