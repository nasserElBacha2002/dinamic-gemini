import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import AnalyticsCompareRedirect from '../src/pages/analytics/AnalyticsCompareRedirect';
import LegacyAisleCompareRedirect from '../src/pages/analytics/LegacyAisleCompareRedirect';

describe('AnalyticsCompareRedirect', () => {
  it('maps legacy jobAId/jobBId query to compare-many jobIds and baseline', async () => {
    const router = createMemoryRouter(
      [
        { path: '/inventories/:inventoryId/analytics/compare', element: <AnalyticsCompareRedirect /> },
        { path: '/inventories/:inventoryId/analytics/compare-many', element: <div data-testid="compare-many">ok</div> },
      ],
      {
        initialEntries: ['/inventories/inv-1/analytics/compare?aisleId=a1&jobAId=ja&jobBId=jb'],
      }
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-1/analytics/compare-many');
      const q = new URLSearchParams(router.state.location.search);
      expect(q.get('aisleId')).toBe('a1');
      expect(q.get('jobIds')).toBe('ja,jb');
      expect(q.get('baseline')).toBe('ja');
    });
  });

  it('redirects to compare-many without job mapping when pair is absent', async () => {
    const router = createMemoryRouter(
      [
        { path: '/inventories/:inventoryId/analytics/compare', element: <AnalyticsCompareRedirect /> },
        { path: '/inventories/:inventoryId/analytics/compare-many', element: <div>ok</div> },
      ],
      { initialEntries: ['/inventories/inv-2/analytics/compare'] }
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-2/analytics/compare-many');
      expect(router.state.location.search).toBe('');
    });
  });
});

describe('LegacyAisleCompareRedirect', () => {
  it('redirects old aisle compare URL to compare-many preserving aisle and job selection', async () => {
    const router = createMemoryRouter(
      [
        { path: '/inventories/:inventoryId/aisles/:aisleId/compare', element: <LegacyAisleCompareRedirect /> },
        { path: '/inventories/:inventoryId/analytics/compare-many', element: <div data-testid="compare-many">ok</div> },
      ],
      {
        initialEntries: ['/inventories/inv-x/aisles/aisle-y/compare?jobAId=ja&jobBId=jb'],
      }
    );
    render(<RouterProvider router={router} />);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-x/analytics/compare-many');
      const q = new URLSearchParams(router.state.location.search);
      expect(q.get('aisleId')).toBe('aisle-y');
      expect(q.get('jobIds')).toBe('ja,jb');
      expect(q.get('baseline')).toBe('ja');
    });
  });
});
