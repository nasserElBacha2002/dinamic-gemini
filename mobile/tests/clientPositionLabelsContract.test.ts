/**
 * Mobile unit smoke: client position labels API path builders / contract.
 */

import {
  FUTURE_POSITION_LABEL_SCAN_CONTRACT,
  type ClientPositionLabelQuery,
} from '../src/api/clientPositionLabelsApi';

describe('client position labels mobile contract', () => {
  it('documents future scan ownership as client-scoped', () => {
    expect(FUTURE_POSITION_LABEL_SCAN_CONTRACT.ownership).toContain('client-scoped');
    expect(FUTURE_POSITION_LABEL_SCAN_CONTRACT.type).toBe('DINAMIC_POSITION');
  });

  it('query shape does not require inventory or aisle', () => {
    const query: ClientPositionLabelQuery = { search: 'A-01', page: 1 };
    expect(query).not.toHaveProperty('inventoryId');
    expect(query).not.toHaveProperty('aisleId');
  });
});
