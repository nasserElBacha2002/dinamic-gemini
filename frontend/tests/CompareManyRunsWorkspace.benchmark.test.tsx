import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import * as client from '../src/api/client';
import { CompareManyRunsWorkspace } from '../src/features/analytics/compare/CompareManyRunsWorkspace';
import { AppSnackbarProvider } from '../src/components/ui';
import theme from '../src/theme';
import type { AisleBenchmarkCompareManyResponse, LlmCostSnapshot } from '../src/api/types';

function llmCostSnapshotWithTotal(totalCost = '0.5', currency = 'USD'): LlmCostSnapshot {
  return {
    provider: 'prov-a',
    model: 'model-a',
    billing_currency: currency,
    pricing_available: true,
    usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
    pricing_snapshot: { billing_currency: currency, pricing_source: 'test' },
    computed_cost: { total_cost: totalCost, currency },
    capture_status: 'exact',
    capture_notes: [],
  };
}

function compareManyFixture(): AisleBenchmarkCompareManyResponse {
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
        created_at: '2026-01-01T00:00:00Z',
        execution_time_seconds: 10,
        metrics: {
          raw_rows_considered: 10,
          consolidated_positions: 5,
          total_quantity: 20,
          unknown_internal_code_count: 1,
          needs_review_count: 2,
        },
        llm_cost_snapshot: llmCostSnapshotWithTotal(),
      },
      {
        job_id: 'job-2',
        status: 'succeeded',
        provider_name: 'prov-b',
        model_name: 'model-b',
        created_at: '2026-01-02T00:00:00Z',
        execution_time_seconds: 25,
        metrics: {
          raw_rows_considered: 11,
          consolidated_positions: 6,
          total_quantity: 23,
          unknown_internal_code_count: 2,
          needs_review_count: 1,
        },
        llm_cost_snapshot: llmCostSnapshotWithTotal('0.8'),
      },
    ],
    comparisons: [
      {
        baseline_job_id: 'job-1',
        target_job_id: 'job-2',
        diff_summary: {
          keys_only_in_a: 0,
          keys_only_in_b: 0,
          keys_in_both: 1,
          quantity_changed: 0,
          sku_changed: 0,
          position_code_changed: 0,
        },
        delta: {
          total_quantity_diff: 3,
          consolidated_positions_diff: 1,
          unknown_internal_code_diff: 1,
          needs_review_diff: -1,
          execution_time_delta: 15,
        },
        diff_rows: [],
        diff_rows_truncated: false,
      },
    ],
    summary: {
      job_count: 2,
      baseline_job_id: 'job-1',
      max_total_quantity: 23,
      min_total_quantity: 20,
      max_needs_review: 2,
      min_needs_review: 1,
      max_consolidated_positions: 6,
      min_consolidated_positions: 5,
      max_unknown_internal_code_count: 2,
      min_unknown_internal_code_count: 1,
      min_execution_time_seconds: 10,
      max_execution_time_seconds: 25,
    },
    raw_fetch_truncated: [],
  };
}

function renderEmbeddedWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={queryClient}>
        <AppSnackbarProvider>
          <MemoryRouter>
            <CompareManyRunsWorkspace
              mode="embedded"
              inventoryId="inv-1"
              initialAisleId="aisle-1"
              initialJobIds={['job-1', 'job-2']}
              initialBaselineJobId="job-1"
              inventoryName="Test DC"
            />
          </MemoryRouter>
        </AppSnackbarProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

describe('CompareManyRunsWorkspace embedded benchmark', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getAisles').mockResolvedValue({
      items: [
        {
          id: 'aisle-1',
          inventory_id: 'inv-1',
          code: 'A-01',
          status: 'created',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      page: 1,
      page_size: 200,
      total_items: 1,
      total_pages: 1,
    });
    vi.spyOn(client, 'listAisleJobs').mockResolvedValue({
      jobs: [],
      operational_job_id: 'job-1',
    });
    vi.spyOn(client, 'getAisleBenchmarkCompareMany').mockResolvedValue(compareManyFixture());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders enhanced benchmark blocks in embedded mode', async () => {
    renderEmbeddedWorkspace();
    await waitFor(() => {
      expect(screen.getByTestId('compare-many-results')).toBeInTheDocument();
    });
    expect(screen.getByTestId('compare-benchmark-executive-summary')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-run-cards')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-delta-kpis')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-charts')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-context-warnings')).toHaveAttribute('data-compact', 'true');
  });
});
