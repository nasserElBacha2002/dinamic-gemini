/**
 * Analytics — benchmark compare page (read-only payload, export wiring).
 */

import React from 'react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import { createMemoryRouter, MemoryRouter, Route, Routes, RouterProvider } from 'react-router-dom';
import theme from '../src/theme';
import CompareRunsPage from '../src/pages/analytics/CompareRunsPage';
import LegacyAisleCompareRedirect from '../src/pages/analytics/LegacyAisleCompareRedirect';
import { AppSnackbarProvider } from '../src/components/ui';
import type { AisleBenchmarkCompareResponse } from '../src/api/types';

const hoisted = vi.hoisted(() => {
  const downloadCsvMock = vi.fn().mockResolvedValue(undefined);
  const comparePayload: AisleBenchmarkCompareResponse = {
    inventory_id: 'inv-1',
    aisle_id: 'aisle-1',
    workflow: 'benchmark_compare',
    read_only: true,
    raw_fetch_truncated: { job_a: true, job_b: false },
    run_a: {
      job_id: 'job-a',
      status: 'succeeded',
      provider_name: 'prov',
      model_name: 'mdl',
      prompt_key: 'pk',
      prompt_version: 'v1',
      created_at: '2024-01-01T00:00:00Z',
      metrics: {
        raw_rows_considered: 12,
        consolidated_positions: 6,
        total_quantity: 24,
        unknown_internal_code_count: 0,
        needs_review_count: 1,
      },
      llm_cost_snapshot: {
        provider: 'openai',
        model: 'gpt-4o',
        pricing_available: true,
        billing_currency: 'USD',
        usage: { input_tokens: 100, output_tokens: 50, total_tokens: 150 },
        pricing_snapshot: {
          pricing_source: 'settings.llm_pricing_catalog_json',
          pricing_version: 'catalog-v1',
          billing_currency: 'USD',
        },
        computed_cost: {
          subtotal_input: '0.00050000',
          subtotal_output: '0.00075000',
          total_cost: '0.00125000',
          currency: 'USD',
        },
        capture_status: 'exact',
        capture_notes: [],
      },
    },
    run_b: {
      job_id: 'job-b',
      status: 'succeeded',
      provider_name: 'prov2',
      model_name: 'mdl2',
      prompt_key: 'pk2',
      prompt_version: 'v2',
      created_at: '2024-01-02T00:00:00Z',
      metrics: {
        raw_rows_considered: 11,
        consolidated_positions: 5,
        total_quantity: 22,
        unknown_internal_code_count: 1,
        needs_review_count: 0,
      },
      llm_cost_snapshot: {
        provider: 'claude',
        model: 'claude-sonnet-4',
        pricing_available: false,
        billing_currency: 'USD',
        usage: { input_tokens: 100, output_tokens: 50 },
        pricing_snapshot: {
          pricing_source: 'settings.llm_pricing_catalog_json',
          pricing_version: 'catalog-v1',
          billing_currency: 'USD',
        },
        computed_cost: {
          total_cost: null,
          currency: 'USD',
          total_cost_unavailable_reason: 'pricing_entry_missing',
        },
        capture_status: 'estimated',
        capture_notes: ['pricing_entry_missing'],
      },
    },
    diff_summary: {
      keys_only_in_a: 1,
      keys_only_in_b: 2,
      keys_in_both: 3,
      quantity_changed: 1,
      sku_changed: 0,
      position_code_changed: 1,
    },
    diff_rows: [],
    diff_rows_truncated: false,
  };
  return {
    downloadCsvMock,
    comparePayload,
    inventoryProcessingMode: 'test' as 'production' | 'test',
  };
});

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return { ...actual, downloadAisleBenchmarkExportCsv: hoisted.downloadCsvMock };
});

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => ({
      data: {
        id: 'inv-1',
        name: 'Test Inventory',
        status: 'draft',
        created_at: null,
        processing_mode: hoisted.inventoryProcessingMode,
      },
      isSuccess: true,
      isLoading: false,
      isError: false,
      error: null,
    }),
    useAislesList: () => ({
      data: { items: [{ id: 'aisle-1', code: 'A-01', status: 'created' }] },
      isLoading: false,
      isError: false,
      error: null,
    }),
    useAisleBenchmarkCompare: () => ({
      data: hoisted.comparePayload,
      isFetching: false,
      isError: false,
      error: null,
    }),
    useAisleJobsList: () => ({
      data: { jobs: [], operational_job_id: null },
      isLoading: false,
      isError: false,
      error: null,
    }),
  };
});

function WithShell({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <AppSnackbarProvider>{children}</AppSnackbarProvider>
    </ThemeProvider>
  );
}

describe('CompareRunsPage', () => {
  beforeEach(() => {
    hoisted.downloadCsvMock.mockClear();
    hoisted.inventoryProcessingMode = 'test';
  });

  function renderAt(search: string) {
    const path = `/inventories/inv-1/analytics/compare${search}`;
    return render(
      <WithShell>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/inventories/:inventoryId/analytics/compare" element={<CompareRunsPage />} />
          </Routes>
        </MemoryRouter>
      </WithShell>
    );
  }

  it('renders compare metrics and diff summary for a valid job pair', () => {
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');

    expect(screen.getByTestId('compare-runs-results')).toBeInTheDocument();
    expect(screen.getByText(/info benchmark/i)).toBeInTheDocument();
    expect(screen.getByText(/diff summary title/i)).toBeInTheDocument();
    expect(screen.getByText(/diff summary stats/i)).toBeInTheDocument();
    expect(screen.getByText('job-a')).toBeInTheDocument();
    expect(screen.getByText('job-b')).toBeInTheDocument();
  });

  it('renders total LLM cost and no-pricing fallback for run B', () => {
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');
    expect(screen.getByText('0.00125000 USD')).toBeInTheDocument();
    expect(screen.getByText('No pricing configured')).toBeInTheDocument();
  });

  it('shows operator-friendly tooltip text for cost details', async () => {
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');
    const cells = screen.getAllByText('No pricing configured');
    fireEvent.mouseOver(cells[0]);
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent(/pricing entry missing/i);
    expect(tip).toHaveTextContent(/model in tooltip/i);
  });

  it('shows usage not reported when provider usage is missing', async () => {
    const savedB = { ...hoisted.comparePayload.run_b };
    hoisted.comparePayload.run_b = {
      ...savedB,
      llm_cost_snapshot: {
        provider: 'openai',
        model: 'mdl2',
        pricing_available: true,
        billing_currency: 'USD',
        usage: {},
        pricing_snapshot: {
          pricing_source: 'settings.llm_pricing_catalog_json',
          pricing_version: 'catalog-v1',
          billing_currency: 'USD',
        },
        computed_cost: {
          total_cost: null,
          currency: 'USD',
          total_cost_unavailable_reason: 'provider_usage_missing',
        },
        capture_status: 'unavailable',
        capture_notes: ['provider_usage_missing'],
      },
    };
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');
    expect(screen.getByText('Usage not reported')).toBeInTheDocument();
    fireEvent.mouseOver(screen.getByText('Usage not reported'));
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent(/provider usage missing/i);
    expect(tip).toHaveTextContent(/model in tooltip/i);
    hoisted.comparePayload.run_b = savedB;
  });

  it('shows not computed for other null-cost cases with model in tooltip', async () => {
    const savedB = { ...hoisted.comparePayload.run_b };
    hoisted.comparePayload.run_b = {
      ...savedB,
      model_name: 'custom-model',
      llm_cost_snapshot: {
        provider: 'openai',
        model: 'custom-model',
        pricing_available: true,
        billing_currency: 'USD',
        usage: { input_tokens: 1, output_tokens: 1 },
        pricing_snapshot: {
          pricing_source: 'settings.llm_pricing_catalog_json',
          pricing_version: 'catalog-v1',
          billing_currency: 'USD',
        },
        computed_cost: {
          total_cost: null,
          currency: 'USD',
          total_cost_unavailable_reason: 'cost_not_computed',
        },
        capture_status: 'unavailable',
        capture_notes: [],
      },
    };
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');
    expect(screen.getByText('Not computed')).toBeInTheDocument();
    fireEvent.mouseOver(screen.getByText('Not computed'));
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent(/model in tooltip/i);
    hoisted.comparePayload.run_b = savedB;
  });

  it('shows an honest cap warning when raw fetch hit the server cap', () => {
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');

    const capAlert = screen.getByText(/truncation warning/i).closest('[role="alert"]');
    expect(capAlert).toBeTruthy();
  });

  it('calls benchmark CSV export with the selected job pair', async () => {
    renderAt('?aisleId=aisle-1&jobAId=job-a&jobBId=job-b');

    fireEvent.click(screen.getByRole('button', { name: /export csv/i }));

    await waitFor(() => {
      expect(hoisted.downloadCsvMock).toHaveBeenCalledWith('inv-1', 'aisle-1', {
        jobAId: 'job-a',
        jobBId: 'job-b',
      });
    });
  });

  it('redirects to inventory detail for production inventories', async () => {
    hoisted.inventoryProcessingMode = 'production';
    const router = createMemoryRouter(
      [
        {
          path: '/inventories/:inventoryId/analytics/compare',
          element: <CompareRunsPage />,
        },
        {
          path: '/inventories/:inventoryId',
          element: <div data-testid="inventory-detail-redirect-target" />,
        },
      ],
      {
        initialEntries: ['/inventories/inv-1/analytics/compare?aisleId=aisle-1&jobAId=job-a&jobBId=job-b'],
      },
    );
    render(
      <WithShell>
        <RouterProvider router={router} />
      </WithShell>,
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-1');
    });
  });
});

describe('LegacyAisleCompareRedirect', () => {
  it('redirects old aisle compare URL to analytics compare preserving query params', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/inventories/:inventoryId/aisles/:aisleId/compare',
          element: <LegacyAisleCompareRedirect />,
        },
        {
          path: '/inventories/:inventoryId/analytics/compare',
          element: <div data-testid="analytics-compare-target">ok</div>,
        },
      ],
      {
        initialEntries: ['/inventories/inv-x/aisles/aisle-y/compare?jobAId=ja&jobBId=jb'],
      },
    );
    render(
      <WithShell>
        <RouterProvider router={router} />
      </WithShell>,
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-x/analytics/compare');
      const q = new URLSearchParams(router.state.location.search);
      expect(q.get('aisleId')).toBe('aisle-y');
      expect(q.get('jobAId')).toBe('ja');
      expect(q.get('jobBId')).toBe('jb');
    });
  });
});
