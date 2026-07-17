import { describe, expect, it } from 'vitest';
import { PRIMARY_NAV_ITEMS } from '../src/layout/navConfig';
import { ROUTE_INGESTION_SESSIONS } from '../src/constants/appRoutes';

describe('nav without Sessions', () => {
  it('does not expose ingestion sessions in primary nav', () => {
    expect(PRIMARY_NAV_ITEMS.some((i) => i.to === ROUTE_INGESTION_SESSIONS)).toBe(false);
    expect(PRIMARY_NAV_ITEMS.some((i) => i.labelKey.includes('ingestion'))).toBe(false);
  });
});
