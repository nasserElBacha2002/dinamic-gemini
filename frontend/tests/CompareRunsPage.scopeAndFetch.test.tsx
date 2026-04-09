/**
 * CompareRunsPage scope + URL: no benchmark fetch until jobs are committed to the URL.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import * as client from '../src/api/client';
import CompareRunsPage from '../src/pages/analytics/CompareRunsPage';
import { AppSnackbarProvider } from '../src/components/ui';
import theme from '../src/theme';
import type { Inventory, Aisle, AisleBenchmarkCompareResponse, JobSummary } from '../src/api/types';

const testInventory = (): Inventory => ({
  id: 'inv-1',
  name: 'Test Inv',
  status: 'draft',
  processing_mode: 'test',
});

const testAisle = (id: string, code: string): Aisle => ({
  id,
  inventory_id: 'inv-1',
  code,
  status: 'created',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
});

const testJob = (id: string): JobSummary => ({
  id,
  status: 'succeeded',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
});

const fullComparePayload = (): AisleBenchmarkCompareResponse => ({
  inventory_id: 'inv-1',
  aisle_id: 'aisle-1',
  workflow: 'benchmark_compare',
  read_only: true,
  raw_fetch_truncated: { job_a: false, job_b: false },
  run_a: {
    job_id: 'job-1',
    status: 'succeeded',
    provider_name: 'p',
    model_name: 'm',
    prompt_key: 'k',
    prompt_version: null,
    created_at: '2024-01-01T00:00:00Z',
    metrics: {
      raw_rows_considered: 1,
      consolidated_positions: 1,
      total_quantity: 1,
      unknown_internal_code_count: 0,
      needs_review_count: 0,
    },
  },
  run_b: {
    job_id: 'job-2',
    status: 'succeeded',
    provider_name: 'p',
    model_name: 'm',
    prompt_key: 'k',
    prompt_version: null,
    created_at: '2024-01-02T00:00:00Z',
    metrics: {
      raw_rows_considered: 1,
      consolidated_positions: 1,
      total_quantity: 1,
      unknown_internal_code_count: 0,
      needs_review_count: 0,
    },
  },
  diff_summary: {
    keys_only_in_a: 0,
    keys_only_in_b: 0,
    keys_in_both: 0,
    quantity_changed: 0,
    sku_changed: 0,
    position_code_changed: 0,
  },
  diff_rows: [],
  diff_rows_truncated: false,
});

function renderCompareAt(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: '/inventories/:inventoryId/analytics/compare', element: <CompareRunsPage /> }],
    { initialEntries: [initialEntry] },
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={qc}>
        <AppSnackbarProvider>
          <RouterProvider router={router} />
        </AppSnackbarProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { router, qc };
}

/** Avoid MUI out-of-range Select warnings while aisles load after inventory resolves. */
async function waitForAisleSwitchShowsCode(code: string) {
  await waitFor(() => {
    expect(screen.getByTestId('compare-runs-change-aisle')).toHaveTextContent(code);
  });
}

describe('CompareRunsPage scope and fetch (integration)', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getInventory').mockResolvedValue(testInventory());
    vi.spyOn(client, 'getAisles').mockResolvedValue({
      items: [testAisle('aisle-1', 'A-01'), testAisle('aisle-2', 'B-02')],
      page: 1,
      page_size: 200,
      total_items: 2,
      total_pages: 1,
    });
    vi.spyOn(client, 'listAisleJobs').mockResolvedValue({
      jobs: [testJob('job-1'), testJob('job-2')],
      operational_job_id: 'job-1',
    });
    vi.spyOn(client, 'getAisleBenchmarkCompare').mockResolvedValue(fullComparePayload());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('without query params shows aisle scope and does not call compare API', async () => {
    renderCompareAt('/inventories/inv-1/analytics/compare');
    expect(await screen.findByTestId('compare-runs-aisle-scope')).toBeInTheDocument();
    await waitFor(() => expect(client.getInventory).toHaveBeenCalled());
    await waitFor(() => {
      expect(client.getAisles).toHaveBeenCalled();
    });
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('with only aisleId shows job scope and does not call compare API', async () => {
    renderCompareAt('/inventories/inv-1/analytics/compare?aisleId=aisle-1');
    await waitForAisleSwitchShowsCode('A-01');
    expect(await screen.findByTestId('compare-runs-job-scope')).toBeInTheDocument();
    await waitFor(() => expect(client.listAisleJobs).toHaveBeenCalled());
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();
  });

  it('changing aisle clears job ids from the URL', async () => {
    const { router } = renderCompareAt(
      '/inventories/inv-1/analytics/compare?aisleId=aisle-1&jobAId=job-1&jobBId=job-2',
    );
    await waitForAisleSwitchShowsCode('A-01');
    await screen.findByTestId('compare-runs-results');
    expect(client.getAisleBenchmarkCompare).toHaveBeenCalledTimes(1);

    const changeBox = screen.getByTestId('compare-runs-change-aisle');
    const select = within(changeBox).getByRole('combobox');
    fireEvent.mouseDown(select);
    fireEvent.click(await screen.findByRole('option', { name: 'B-02' }));

    await waitFor(() => {
      const q = new URLSearchParams(router.state.location.search);
      expect(q.get('aisleId')).toBe('aisle-2');
      expect(q.get('jobAId')).toBeNull();
      expect(q.get('jobBId')).toBeNull();
    });
  });

  it('load comparison updates URL and triggers compare fetch', async () => {
    renderCompareAt('/inventories/inv-1/analytics/compare?aisleId=aisle-1');
    await waitForAisleSwitchShowsCode('A-01');
    await screen.findByTestId('compare-runs-job-scope');
    expect(client.getAisleBenchmarkCompare).not.toHaveBeenCalled();

    const loadBtn = await screen.findByRole('button', { name: /load comparison/i });
    await waitFor(() => expect(loadBtn).not.toBeDisabled());
    fireEvent.click(loadBtn);

    await waitFor(() => {
      expect(client.getAisleBenchmarkCompare).toHaveBeenCalledWith('inv-1', 'aisle-1', 'job-1', 'job-2');
    });
    expect(await screen.findByTestId('compare-runs-results')).toBeInTheDocument();
  });
});
