import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import * as client from '../src/api/client';
import CompareManyRunsPage from '../src/pages/analytics/CompareManyRunsPage';
import { AppSnackbarProvider } from '../src/components/ui';
import theme from '../src/theme';
import type { AisleBenchmarkCompareManyResponse, Inventory, Aisle, JobSummary } from '../src/api/types';

const inventoryFixture = (): Inventory => ({
  id: 'inv-1',
  name: 'Test Inventory',
  status: 'draft',
  processing_mode: 'test',
});

const aisleFixture = (id: string, code: string): Aisle => ({
  id,
  inventory_id: 'inv-1',
  code,
  status: 'created',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

const jobFixture = (id: string, status = 'succeeded'): JobSummary => ({
  id,
  status,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

function compareManyFixture(includeDiffRows: boolean): AisleBenchmarkCompareManyResponse {
  return {
    inventory_id: 'inv-1',
    aisle_id: 'aisle-1',
    workflow: 'benchmark_compare_many',
    read_only: true,
    baseline_job_id: 'job-1',
    jobs: [
      {
        job_id: 'job-1',
        status: 'succeeded',
        provider_name: 'prov-a',
        model_name: 'model-a',
        prompt_key: 'pk-a',
        prompt_version: 'v1',
        created_at: '2026-01-01T00:00:00Z',
        metrics: {
          raw_rows_considered: 10,
          consolidated_positions: 5,
          total_quantity: 20,
          unknown_internal_code_count: 1,
          needs_review_count: 2,
        },
      },
      {
        job_id: 'job-2',
        status: 'succeeded',
        provider_name: 'prov-b',
        model_name: 'model-b',
        prompt_key: 'pk-b',
        prompt_version: 'v2',
        created_at: '2026-01-02T00:00:00Z',
        metrics: {
          raw_rows_considered: 11,
          consolidated_positions: 6,
          total_quantity: 23,
          unknown_internal_code_count: 2,
          needs_review_count: 1,
        },
      },
      {
        job_id: 'job-3',
        status: 'running',
        provider_name: 'prov-c',
        model_name: 'model-c',
        prompt_key: 'pk-c',
        prompt_version: 'v3',
        created_at: '2026-01-03T00:00:00Z',
        metrics: {
          raw_rows_considered: 9,
          consolidated_positions: 7,
          total_quantity: 19,
          unknown_internal_code_count: 4,
          needs_review_count: 3,
        },
      },
    ],
    comparisons: [
      {
        baseline_job_id: 'job-1',
        target_job_id: 'job-2',
        diff_summary: {
          keys_only_in_a: 1,
          keys_only_in_b: 0,
          keys_in_both: 4,
          quantity_changed: 1,
          sku_changed: 0,
          position_code_changed: 0,
        },
        delta: {
          total_quantity_diff: 3,
          consolidated_positions_diff: 1,
          unknown_internal_code_diff: 1,
          needs_review_diff: -1,
        },
        diff_rows: includeDiffRows
          ? [
              {
                match_key: 'k1',
                side: 'both',
                quantity_a: 2,
                quantity_b: 4,
                sku_a: 'sku-a',
                sku_b: 'sku-b',
                position_code_a: 'P-A',
                position_code_b: 'P-B',
              },
            ]
          : [],
        diff_rows_truncated: false,
      },
      {
        baseline_job_id: 'job-1',
        target_job_id: 'job-3',
        diff_summary: {
          keys_only_in_a: 0,
          keys_only_in_b: 0,
          keys_in_both: 5,
          quantity_changed: 0,
          sku_changed: 0,
          position_code_changed: 0,
        },
        delta: {
          total_quantity_diff: -1,
          consolidated_positions_diff: 2,
          unknown_internal_code_diff: 3,
          needs_review_diff: 1,
        },
        diff_rows: includeDiffRows ? [] : [],
        diff_rows_truncated: false,
      },
    ],
    summary: {
      job_count: 3,
      baseline_job_id: 'job-1',
      max_total_quantity: 23,
      min_total_quantity: 19,
      max_needs_review: 3,
      min_needs_review: 1,
      max_consolidated_positions: 7,
      min_consolidated_positions: 5,
      max_unknown_internal_code_count: 4,
      min_unknown_internal_code_count: 1,
    },
    raw_fetch_truncated: [
      { job_id: 'job-1', truncated: false },
      { job_id: 'job-2', truncated: false },
      { job_id: 'job-3', truncated: false },
    ],
  };
}

function renderPage(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: '/inventories/:inventoryId/analytics/compare-many', element: <CompareManyRunsPage /> }],
    { initialEntries: [initialEntry] }
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={queryClient}>
        <AppSnackbarProvider>
          <RouterProvider router={router} />
        </AppSnackbarProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
  return { router };
}

describe('CompareManyRunsPage', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getInventory').mockResolvedValue(inventoryFixture());
    vi.spyOn(client, 'getAisles').mockResolvedValue({
      items: [aisleFixture('aisle-1', 'A-01'), aisleFixture('aisle-2', 'B-02')],
      page: 1,
      page_size: 200,
      total_items: 2,
      total_pages: 1,
    });
    vi.spyOn(client, 'listAisleJobs').mockResolvedValue({
      jobs: [jobFixture('job-1'), jobFixture('job-2'), jobFixture('job-3', 'running')],
      operational_job_id: 'job-1',
    });
    vi.spyOn(client, 'getAisleBenchmarkCompareMany').mockImplementation(async (_inv, _aisle, body) => {
      return compareManyFixture(Boolean(body.include_diff_rows));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('parses applied URL state and fetches compare-many with includeDiffRows=false', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledWith('inv-1', 'aisle-1', {
        job_ids: ['job-1', 'job-2'],
        baseline_job_id: 'job-1',
        include_diff_rows: false,
        max_diff_rows: undefined,
      });
    });
    expect(await screen.findByTestId('compare-many-results')).toBeInTheDocument();
  });

  it('keeps draft changes local until apply, then updates URL and refetches', async () => {
    const { router } = renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await waitFor(() => expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(1));

    fireEvent.mouseDown(screen.getByLabelText('Baseline'));
    fireEvent.click(await screen.findByRole('option', { name: /job-2/i }));
    expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /apply comparison/i }));
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(2);
      expect(new URLSearchParams(router.state.location.search).get('baseline')).toBe('job-2');
    });
  });

  it('auto-corrects invalid baseline in URL and shows one-shot notice', async () => {
    const { router } = renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-x');
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get('baseline')).toBe('job-1');
    });
    expect(screen.getByText('Baseline adjusted to match current selection.')).toBeInTheDocument();
  });

  it('renders 3-job view with baseline card highlighted and target ordering', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByTestId('compare-many-baseline-card')).toBeInTheDocument();
    const blocks = screen.getAllByTestId('compare-many-comparison-block');
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toHaveTextContent(/job-2/i);
    expect(blocks[1]).toHaveTextContent(/job-3/i);
  });

  it('keeps diff rows collapsed by default and loads on demand when expanded', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.queryByTestId('compare-many-diff-rows-panel')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /show diff rows/i })[0]);
    await waitFor(() => {
      const calls = vi.mocked(client.getAisleBenchmarkCompareMany).mock.calls;
      expect(calls.some((call) => Boolean(call[2].include_diff_rows))).toBe(true);
    });
    expect(await screen.findByTestId('compare-many-diff-rows-panel')).toBeInTheDocument();
  });

  it('shows empty instructional state when applied selection is insufficient', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1&baseline=job-1');
    expect(await screen.findByTestId('compare-many-empty-state')).toBeInTheDocument();
    expect(client.getAisleBenchmarkCompareMany).not.toHaveBeenCalled();
  });
});
