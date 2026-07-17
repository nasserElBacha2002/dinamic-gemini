import { getAisleCreationRules } from '../src/features/aisles/aisleCreationRules';

describe('aisleCreationRules', () => {
  it('documents supplier required when inventory has client', () => {
    const rules = getAisleCreationRules({ client_id: 'client-1' });
    expect(rules.supplierRequired).toBe(true);
    expect(rules.reason).toMatch(/proveedor/i);
  });

  it('still requires supplier path when inventory lacks client', () => {
    const rules = getAisleCreationRules({ client_id: null });
    expect(rules.inventoryClientRequired).toBe(true);
    expect(rules.supplierRequired).toBe(true);
  });
});
