import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import * as client from '../src/api/client';
import CompareManyRunsPage from '../src/pages/analytics/CompareManyRunsPage';
import { buildDraftError } from '../src/features/analytics/compare/compareManyRunsDraft';
import { AppSnackbarProvider } from '../src/components/ui';
import theme from '../src/theme';
import type { AisleBenchmarkCompareManyResponse, Inventory, Aisle, JobSummary, LlmCostSnapshot } from '../src/api/types';

function llmCostSnapshotWithTotal(totalCost = '0.123400', currency = 'USD'): LlmCostSnapshot {
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
  provider_name: id === 'job-1' ? 'prov-a' : id === 'job-2' ? 'prov-b' : 'prov-c',
  model_name: id === 'job-1' ? 'model-a' : id === 'job-2' ? 'model-b' : 'model-c',
  ...(id === 'job-1' ? { llm_cost_snapshot: llmCostSnapshotWithTotal() } : {}),
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
        execution_time_seconds: 10,
        execution_time_human: '10s',
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
        prompt_key: 'pk-b',
        prompt_version: 'v2',
        created_at: '2026-01-02T00:00:00Z',
        execution_time_seconds: 25,
        execution_time_human: '25s',
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
          execution_time_delta: 15,
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
          execution_time_delta: null,
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

    fireEvent.mouseDown(screen.getByLabelText(/baseline/i));
    fireEvent.click(await screen.findByRole('option', { name: /prov-b · model-b/i }));
    expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /apply comparison|aplicar comparación/i }));
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(2);
      expect(new URLSearchParams(router.state.location.search).get('baseline')).toBe('job-2');
    });
  });

  it('shows changes-not-applied indicator when draft differs from applied state', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await waitFor(() => expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalledTimes(1));
    fireEvent.mouseDown(screen.getByLabelText(/baseline/i));
    fireEvent.click(await screen.findByRole('option', { name: /prov-b · model-b/i }));
    expect(screen.getByText(/changes not applied|hay cambios sin aplicar/i)).toBeInTheDocument();
  });

  it('auto-corrects invalid baseline in URL and shows one-shot notice', async () => {
    const { router } = renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-x');
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get('baseline')).toBe('job-1');
    });
    expect(
      screen.getByText(/baseline adjusted to match current selection|ajustó la baseline/i),
    ).toBeInTheDocument();
  });

  it('does not rewrite other invalid URL states and does not fetch compare-many', async () => {
    const { router } = renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3,job-4&baseline=job-1');
    expect(await screen.findByTestId('compare-many-empty-state')).toBeInTheDocument();
    await waitFor(() => {
      expect(client.getAisleBenchmarkCompareMany).not.toHaveBeenCalled();
    });
    expect(router.state.location.search).toContain('jobIds=job-1,job-2,job-3,job-4');
  });

  it('renders 3-job view with baseline card highlighted and target ordering', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByTestId('compare-many-baseline-card')).toBeInTheDocument();
    const blocks = screen.getAllByTestId('compare-many-comparison-block');
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toHaveTextContent(/model-b|prov-b/i);
    expect(blocks[1]).toHaveTextContent(/model-c|prov-c/i);
  });

  it('renders status as dedicated chip and keeps provider-model metadata separate', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByText(/Estado:.*(En ejecución|Running)|status:.*running/i)).toBeInTheDocument();
    expect(screen.getAllByText(/prov-c · model-c/i).length).toBeGreaterThanOrEqual(1);
  });

  it('run cards show cost line when compare-many payload includes llm_cost_snapshot with total_cost', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    const baselineCard = screen.getByTestId('compare-many-baseline-card');
    expect(baselineCard).toHaveTextContent(/Costo por corrida|Cost per run/i);
    expect(baselineCard).toHaveTextContent(/0\.123400|0\.1234/i);
  });

  it('run cards show cost unavailable when llm_cost_snapshot is missing', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    const unavailable = screen.getAllByText(/No disponible|Not available|Sin snapshot|no snapshot/i);
    expect(unavailable.length).toBeGreaterThanOrEqual(2);
  });

  it('run picker option includes cost in secondary line when JobSummary has llm_cost_snapshot', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await waitFor(() => expect(client.getAisleBenchmarkCompareMany).toHaveBeenCalled());
    fireEvent.mouseDown(screen.getByLabelText(/runs to compare|corridas a comparar/i));
    const opt = await screen.findByRole('option', { name: /prov-a · model-a/i });
    expect(opt.textContent).toMatch(/0\.123400|0\.1234/);
    expect(opt.textContent).toMatch(/USD/);
  });

  it('adjusts draft baseline when selection removes current baseline and applies corrected baseline', async () => {
    const { router } = renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await screen.findByTestId('compare-many-results');

    fireEvent.mouseDown(screen.getByLabelText(/runs to compare|corridas a comparar/i));
    fireEvent.click(await screen.findByRole('option', { name: /prov-c · model-c/i }));
    fireEvent.click(await screen.findByRole('option', { name: /prov-a · model-a/i }));
    fireEvent.keyDown(screen.getByRole('listbox', { name: /runs to compare|corridas a comparar/i }), {
      key: 'Escape',
    });
    fireEvent.click(screen.getByRole('button', { name: /apply comparison|aplicar comparación/i }));

    await waitFor(() => {
      const params = new URLSearchParams(router.state.location.search);
      const jobIds = (params.get('jobIds') ?? '').split(',').filter(Boolean);
      expect(params.get('baseline')).toBeTruthy();
      expect(jobIds).toContain(params.get('baseline') as string);
      expect(params.get('baseline')).not.toBe('job-1');
    });
  });

  it('keeps diff rows collapsed by default and loads on demand when expanded', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.queryByTestId('compare-many-diff-rows-panel')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /show diff rows|ver filas con diferencias/i })[0]);
    await waitFor(() => {
      const calls = vi.mocked(client.getAisleBenchmarkCompareMany).mock.calls;
      expect(calls.some((call) => Boolean(call[2].include_diff_rows))).toBe(true);
      expect(calls.some((call) => Boolean(call[2].include_diff_rows) && call[2].job_ids.join(',') === 'job-1,job-2')).toBe(
        true
      );
    });
    expect(await screen.findByTestId('compare-many-diff-rows-panel')).toBeInTheDocument();
  });

  it('shows empty instructional state when applied selection is insufficient', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1&baseline=job-1');
    expect(await screen.findByTestId('compare-many-empty-state')).toBeInTheDocument();
    expect(client.getAisleBenchmarkCompareMany).not.toHaveBeenCalled();
  });

  it('keeps controls usable when compare-many request errors', async () => {
    vi.mocked(client.getAisleBenchmarkCompareMany).mockRejectedValueOnce(new Error('boom'));
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByLabelText(/baseline/i));
    fireEvent.click(await screen.findByRole('option', { name: /prov-b · model-b/i }));
    expect(screen.getByText(/changes not applied|hay cambios sin aplicar/i)).toBeInTheDocument();
  });

  it('renders executive summary quantity range and per-run consolidated metrics', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByText(/Cantidad mínima|Min \/ max quantity/i)).toBeInTheDocument();
    expect(screen.getByText(/19 – 23|19 - 23/)).toBeInTheDocument();
    expect(screen.getAllByText(/Posiciones consolidadas|Consolidated positions/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Códigos internos desconocidos|Unknown internal codes/i).length).toBeGreaterThanOrEqual(1);
  });

  it('surfaces wall-clock execution time on job cards and delta when present', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    const runCards = screen.getByTestId('compare-benchmark-run-cards');
    expect(within(runCards).getAllByText(/10s/).length).toBeGreaterThanOrEqual(1);
    expect(within(runCards).getAllByText(/25s/).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(/Wall time \(target − baseline\): \+15s|Tiempo de pared \(target − baseline\): \+15s/i),
    ).toBeInTheDocument();
  });

  it('helper validation flags duplicate and baseline-outside-selection drafts', () => {
    expect(buildDraftError('aisle-1', ['job-1', 'job-1'], 'job-1', (k) => k)).toBe('compare_many.errors.duplicate_jobs');
    expect(buildDraftError('aisle-1', ['job-1', 'job-2'], 'job-3', (k) => k)).toBe(
      'compare_many.errors.pick_valid_baseline'
    );
  });

  it('helper validation flags too-few selections for draft apply', () => {
    expect(buildDraftError('aisle-1', ['job-1'], 'job-1', (k) => k)).toBe('compare_many.errors.pick_two_jobs');
  });

  it('renders benchmark executive summary and context warnings after compare', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByTestId('compare-benchmark-executive-summary')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-context-warnings')).toBeInTheDocument();
    expect(screen.getByText(/Resumen de comparación|Comparison summary/i)).toBeInTheDocument();
    expect(
      screen.getByText(/no recomienda automáticamente|does not automatically recommend/i)
    ).toBeInTheDocument();
  });

  it('renders benchmark run cards with cost per unit and charts', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getByTestId('compare-benchmark-run-cards')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-delta-kpis')).toBeInTheDocument();
    expect(screen.getByTestId('compare-benchmark-charts')).toBeInTheDocument();
    expect(screen.getByTestId('compare-chart-cost-per-run-card')).toBeInTheDocument();
    expect(screen.getAllByText(/Costo por unidad|Cost per unit/i).length).toBeGreaterThanOrEqual(1);
  });

  it('shows cost per unit unavailable on cards without cost snapshot', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2,job-3&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    const unavailable = screen.getAllByText(/No disponible|Not available/i);
    expect(unavailable.length).toBeGreaterThanOrEqual(2);
  });

  it('renders difference summary in comparison blocks', async () => {
    renderPage('/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1');
    await screen.findByTestId('compare-many-results');
    expect(screen.getAllByTestId('compare-difference-summary').length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/Expandí el detalle|Expand details/i).length
    ).toBeGreaterThanOrEqual(1);
  });

  it('redirects production inventories away from compare-many to inventory detail', async () => {
    vi.mocked(client.getInventory).mockResolvedValue({
      ...inventoryFixture(),
      processing_mode: 'production',
    });
    const { router } = renderPage(
      '/inventories/inv-1/analytics/compare-many?aisleId=aisle-1&jobIds=job-1,job-2&baseline=job-1'
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/inventories/inv-1');
    });
  });
});
