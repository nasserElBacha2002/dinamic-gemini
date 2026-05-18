import { describe, it, expect } from 'vitest';
import { buildFilterParams } from '../src/features/analytics-dashboard/types';

describe('buildFilterParams costSummary', () => {
  it('maps dashboard filters to cost-summary snake_case params', () => {
    const params = buildFilterParams({
      dateFrom: '2026-01-01',
      dateTo: '2026-01-31',
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      clientId: 'client-1',
      clientSupplierId: 'sup-1',
      providerName: 'gemini',
      modelName: 'flash',
    });

    expect(params.costSummary).toEqual({
      date_from: '2026-01-01',
      date_to: '2026-01-31',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
      client_id: 'client-1',
      client_supplier_id: 'sup-1',
      provider_name: 'gemini',
      model_name: 'flash',
    });
  });

  it('does not send empty string params', () => {
    const params = buildFilterParams({
      dateFrom: '',
      dateTo: '',
      inventoryId: '',
      aisleId: '',
      clientId: '   ',
      clientSupplierId: '',
      providerName: '',
      modelName: '  ',
    });

    expect(params.costSummary).toEqual({});
    expect(Object.values(params.costSummary).every((v) => v !== '')).toBe(true);
  });
});
