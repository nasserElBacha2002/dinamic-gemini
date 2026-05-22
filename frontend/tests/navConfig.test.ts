import { describe, it, expect } from 'vitest';
import { PRIMARY_NAV_ITEMS } from '../src/layout/navConfig';

describe('navConfig', () => {
  it('exposes a single analytics nav entry', () => {
    const analyticsItems = PRIMARY_NAV_ITEMS.filter((item) => item.labelKey === 'nav.analytics');
    expect(analyticsItems).toHaveLength(1);
    expect(analyticsItems[0]?.to).toContain('/analitica?tab=resumen');
  });

  it('does not expose legacy metrics or observability nav items', () => {
    const labels = PRIMARY_NAV_ITEMS.map((item) => item.labelKey);
    expect(labels).not.toContain('nav.metrics');
    expect(labels).not.toContain('nav.observability');
  });
});
