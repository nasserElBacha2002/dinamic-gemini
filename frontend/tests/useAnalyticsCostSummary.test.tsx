import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAnalyticsCostSummary } from '../src/hooks/useAnalyticsCostSummary';
import * as analyticsApi from '../src/api/analyticsApi';
import { EMPTY_ANALYTICS_COST_SCOPE } from './helpers/fixtures';

vi.mock('../src/api/analyticsApi', async () => {
  const actual = await vi.importActual<typeof import('../src/api/analyticsApi')>('../src/api/analyticsApi');
  return {
    ...actual,
    getAnalyticsCostSummary: vi.fn(),
  };
});

const mockGetCostSummary = vi.mocked(analyticsApi.getAnalyticsCostSummary);

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCostSummary.mockResolvedValue({
    scope: EMPTY_ANALYTICS_COST_SCOPE,
    totals: { jobs_total: 1, jobs_with_cost: 1, jobs_without_cost: 0 } as never,
    by_provider_model: [],
    by_inventory: [],
    by_aisle: [],
    by_capture_status: [],
    warnings: [],
  });
});

describe('useAnalyticsCostSummary', () => {
  it('calls GET cost-summary with filter params', async () => {
    const { result } = renderHook(
      () =>
        useAnalyticsCostSummary({
          date_from: '2026-01-01',
          date_to: '2026-01-31',
          inventory_id: 'inv-1',
        }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetCostSummary).toHaveBeenCalledWith({
      date_from: '2026-01-01',
      date_to: '2026-01-31',
      inventory_id: 'inv-1',
    });
  });
});
