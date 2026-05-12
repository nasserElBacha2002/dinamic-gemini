import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import ObservabilityMetricsPage from '../src/pages/ObservabilityMetricsPage';

const mockUseObservabilityMetrics = vi.fn();

vi.mock('../src/hooks/useObservabilityMetrics', () => ({
  useObservabilityMetrics: (...args: unknown[]) => mockUseObservabilityMetrics(...args),
}));

function sampleMetrics(overrides: Partial<{ jobs_without: number; runs_total: number }> = {}) {
  const runs = overrides.runs_total ?? 2;
  const without = overrides.jobs_without ?? 0;
  const succeeded = runs === 0 ? 0 : 1;
  const failed = runs === 0 ? 0 : 1;
  return {
    range: { from: '2026-01-01T00:00:00Z', to: '2026-01-31T00:00:00Z' },
    filters: {
      client_id: null,
      client_supplier_id: null,
      provider_name: null,
      model_name: null,
    },
    totals: {
      runs_total: runs,
      runs_succeeded: succeeded,
      runs_failed: failed,
      success_rate: runs === 0 ? null : 0.5,
      failure_rate: runs === 0 ? null : 0.5,
      fallback_runs: runs === 0 ? 0 : 1,
      missing_prompt_config_runs: runs === 0 ? 0 : 1,
      missing_reference_runs: runs === 0 ? 0 : 1,
      legacy_runs: runs === 0 ? 0 : 1,
    },
    by_client:
      runs === 0
        ? []
        : [
            {
              client_id: 'c-1',
              runs_total: 2,
              runs_succeeded: 1,
              runs_failed: 1,
              failure_rate: 0.5,
            },
          ],
    by_supplier:
      runs === 0
        ? []
        : [
            {
              client_supplier_id: 's-1',
              client_id: 'c-1',
              runs_total: 2,
              runs_succeeded: 1,
              runs_failed: 1,
              fallback_runs: 1,
              missing_reference_runs: 0,
              failure_rate: 0.5,
            },
          ],
    by_provider_model:
      runs === 0
        ? []
        : [
            {
              provider_name: 'gemini',
              model_name: 'flash',
              runs_total: 2,
              runs_succeeded: 1,
              runs_failed: 1,
              failure_rate: 0.5,
            },
          ],
    data_quality: {
      jobs_with_audit_snapshot: runs - without,
      jobs_without_audit_snapshot: without,
      jobs_with_missing_metadata: 0,
      artifact_dependent_jobs: 0,
    },
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ObservabilityMetricsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ObservabilityMetricsPage', () => {
  beforeEach(() => {
    mockUseObservabilityMetrics.mockReset();
  });

  it('renders loading copy', () => {
    mockUseObservabilityMetrics.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Cargando métricas de observabilidad…')).toBeInTheDocument();
  });

  it('happy path shows KPIs and table rows', async () => {
    mockUseObservabilityMetrics.mockReturnValue({
      data: sampleMetrics({ jobs_without: 0, runs_total: 2 }),
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Métricas de observabilidad' })).toBeInTheDocument();
    expect(screen.getAllByText('Procesamientos').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Exitosos').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Fallidos').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Tasa de error').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Fallbacks').length).toBeGreaterThanOrEqual(1);
    const c1 = screen.getAllByRole('cell', { name: 'c-1' });
    expect(c1.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('cell', { name: 's-1' })).toBeInTheDocument();
  });

  it('empty state when runs_total is 0', () => {
    mockUseObservabilityMetrics.mockReturnValue({
      data: sampleMetrics({ runs_total: 0, jobs_without: 0 }),
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('No hay procesamientos para los filtros seleccionados.')).toBeInTheDocument();
  });

  it('partial data note when jobs lack audit snapshot', () => {
    mockUseObservabilityMetrics.mockReturnValue({
      data: sampleMetrics({ jobs_without: 2, runs_total: 2 }),
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(
      screen.getByText(
        'Algunas métricas pueden ser parciales porque existen jobs sin snapshot de auditoría.'
      )
    ).toBeInTheDocument();
  });

  it('error state shows Spanish message', () => {
    mockUseObservabilityMetrics.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error(),
      isFetching: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('No se pudieron cargar las métricas de observabilidad.')).toBeInTheDocument();
  });
});
