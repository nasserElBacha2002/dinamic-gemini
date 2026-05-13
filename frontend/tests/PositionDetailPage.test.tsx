/**
 * Deep link `/positions/:id` redirects to list views with openReviewDrawer state (single review UX).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import PositionDetailPage from '../src/pages/PositionDetailPage';

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => ({
      data: { id: 'inv-1', name: 'Test Inventory', status: 'draft' as const, created_at: null },
      isLoading: false,
      isError: false,
      error: null,
      isFetched: true,
    }),
    useAislesList: () => ({
      data: { items: [{ id: 'aisle-1', code: 'A-01', status: 'created' as const }] },
      isLoading: false,
      isError: false,
      error: null,
      isFetched: true,
    }),
  };
});

describe('PositionDetailPage (redirect)', () => {
  it('redirects to aisle results with openReviewDrawer payload', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/inventories/:inventoryId/aisles/:aisleId/positions/:positionId',
          element: <PositionDetailPage />,
        },
        {
          path: '/inventories/:inventoryId/aisles/:aisleId/positions',
          element: <div data-testid="aisle-list" />,
        },
      ],
      { initialEntries: ['/inventories/inv-1/aisles/aisle-1/positions/pos-1'] }
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-1/aisles/aisle-1/positions');
      const st = router.state.location.state as { openReviewDrawer?: { kind: string; positionId: string } };
      expect(st?.openReviewDrawer?.kind).toBe('aisle');
      expect(st?.openReviewDrawer?.positionId).toBe('pos-1');
    });
  });

  it('redirects to aisle results with openReviewDrawer when returnTo is legacy review_queue', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/inventories/:inventoryId/aisles/:aisleId/positions/:positionId',
          element: <PositionDetailPage />,
        },
        {
          path: '/inventories/:inventoryId/aisles/:aisleId/positions',
          element: <div data-testid="aisle-list" />,
        },
      ],
      {
        initialEntries: [
          {
            pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-x',
            state: { resultIds: ['a', 'b'], returnTo: 'review_queue' },
          },
        ],
      }
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-1/aisles/aisle-1/positions');
      const st = router.state.location.state as {
        openReviewDrawer?: { kind: string; positionId: string; resultIds: string[] };
      };
      expect(st?.openReviewDrawer?.kind).toBe('aisle');
      expect(st?.openReviewDrawer?.positionId).toBe('pos-x');
      expect(st?.openReviewDrawer?.resultIds).toEqual(['a', 'b']);
    });
  });
});
