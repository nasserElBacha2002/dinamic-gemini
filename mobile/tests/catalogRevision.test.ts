import { computeCatalogRevision } from '../src/features/catalog/catalogRevision';

describe('catalog revision', () => {
  it('is stable regardless of input order', () => {
    const base = {
      inventories: [
        {
          id: 'inv-b',
          client_id: 'client-1',
          name: 'Beta',
          status: 'active',
          updated_at: '2026-01-02T00:00:00Z',
          processing_mode: 'production',
        },
        {
          id: 'inv-a',
          client_id: 'client-1',
          name: 'Alpha',
          status: 'active',
          updated_at: '2026-01-01T00:00:00Z',
          processing_mode: 'production',
        },
      ],
      aisles: [
        {
          id: 'aisle-2',
          inventory_id: 'inv-a',
          code: 'B02',
          status: 'created',
          updated_at: '2026-01-01T01:00:00Z',
          is_active: true,
        },
        {
          id: 'aisle-1',
          inventory_id: 'inv-a',
          code: 'A01',
          status: 'created',
          updated_at: '2026-01-01T00:30:00Z',
          is_active: true,
        },
      ],
      suppliers: [
        {
          id: 'sup-2',
          client_id: 'client-1',
          name: 'Supplier B',
          status: 'active',
          updated_at: '2026-01-01T02:00:00Z',
        },
        {
          id: 'sup-1',
          client_id: 'client-1',
          name: 'Supplier A',
          status: 'active',
          updated_at: '2026-01-01T01:30:00Z',
        },
      ],
    };
    const forward = computeCatalogRevision(base);
    const reversed = computeCatalogRevision({
      inventories: [...base.inventories].reverse(),
      aisles: [...base.aisles].reverse(),
      suppliers: [...base.suppliers].reverse(),
    });
    expect(forward).toBe(reversed);
    expect(forward).toMatch(/^[0-9a-f]{64}$/);
  });

  it('changes when supplier status changes', () => {
    const before = computeCatalogRevision({
      inventories: [],
      aisles: [],
      suppliers: [
        {
          id: 'sup-1',
          client_id: 'client-1',
          name: 'Supplier A',
          status: 'active',
          updated_at: '2026-01-01T01:30:00Z',
        },
      ],
    });
    const after = computeCatalogRevision({
      inventories: [],
      aisles: [],
      suppliers: [
        {
          id: 'sup-1',
          client_id: 'client-1',
          name: 'Supplier A',
          status: 'inactive',
          updated_at: '2026-01-01T01:30:00Z',
        },
      ],
    });
    expect(before).not.toBe(after);
  });
});
