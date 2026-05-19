import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  createMemoryRouter,
  MemoryRouter,
  Route,
  RouterProvider,
  Routes,
  useLocation,
} from 'react-router-dom';
import AnalyticsDashboardPage from '../src/features/analytics-dashboard/AnalyticsDashboardPage';
import MetricsLegacyRedirect from '../src/pages/analytics/MetricsLegacyRedirect';
import ObservabilityLegacyRedirect from '../src/pages/analytics/ObservabilityLegacyRedirect';
import { pathToAnalytics } from '../src/constants/appRoutes';
import { analyticsTabToUrl, parseAnalyticsTab } from '../src/constants/analyticsTabs';

const mockUseAuth = vi.fn();
const mockUseAnalyticsDashboardData = vi.fn();
const mockUseInventoriesList = vi.fn();

vi.mock('../src/features/auth', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../src/features/analytics-dashboard/hooks/useAnalyticsDashboardData', () => ({
  useAnalyticsDashboardData: (...args: unknown[]) => mockUseAnalyticsDashboardData(...args),
}));

vi.mock('../src/hooks/useInventories', () => ({
  useInventoriesList: (...args: unknown[]) => mockUseInventoriesList(...args),
}));

vi.mock('../src/hooks/useAisles', () => ({
  useAislesList: () => ({ data: { items: [] }, isLoading: false }),
  useAisleJobsList: () => ({ data: { jobs: [] }, isLoading: false }),
  useInventoryMetrics: () => ({ data: null, isLoading: false, isError: false }),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>;
}

function renderAnalyticsAt(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/analitica" element={<AnalyticsDashboardPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderAnalyticsRouter(initialEntries: string[], initialIndex?: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      {
        path: '/analitica',
        element: (
          <QueryClientProvider client={client}>
            <AnalyticsDashboardPage />
          </QueryClientProvider>
        ),
      },
    ],
    { initialEntries, initialIndex }
  );
  return { router, ...render(<RouterProvider router={router} />) };
}

const analyticsLoaded = {
  summary: {
    auto_acceptance_rate: 0.5,
    manual_correction_rate: 0.25,
    unidentified_product_rate: 0.15,
    invalid_traceability_rate: 0.1,
    processing_success_rate: 0.9,
    average_processing_time_seconds: 120,
    average_processing_time_minutes: 2,
    processed_positions_count: 16,
    reviewed_positions_count: 8,
    total_positions_in_scope: 20,
    notes: [],
  },
  trends: {
    reviewed_results_over_time: [],
    correction_rate_over_time: [],
    processing_success_over_time: [],
  },
  inventoryPerformance: { items: [] },
  aisleIssues: { items: [] },
  qualityPatterns: { items: [] },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuth.mockReturnValue({ initialized: true, user: { username: 'tester' } });
  mockUseInventoriesList.mockReturnValue({
    data: { items: [{ id: 'inv-1', name: 'Test', processing_mode: 'test' }] },
    isError: false,
  });
  mockUseAnalyticsDashboardData.mockReturnValue({
    analytics: analyticsLoaded,
    observability: { data: null, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    costSummary: { data: null, isLoading: false, isError: false, error: null, refetch: vi.fn() },
    isAnalyticsLoading: false,
    isObservabilityLoading: false,
    isCostSummaryLoading: false,
    analyticsError: null,
    observabilityError: null,
    costSummaryError: null,
    hasMixedLoadedData: false,
    refetchAll: vi.fn(),
  });
});

describe('analyticsTabs helpers', () => {
  it('parseAnalyticsTab defaults invalid values to summary', () => {
    expect(parseAnalyticsTab(null)).toBe('summary');
    expect(parseAnalyticsTab('invalid-tab')).toBe('summary');
    expect(parseAnalyticsTab('costos')).toBe('costs');
  });

  it('pathToAnalytics builds tab query URLs', () => {
    expect(pathToAnalytics()).toBe('/analitica?tab=resumen');
    expect(pathToAnalytics('costs')).toBe('/analitica?tab=costos');
    expect(pathToAnalytics('compare')).toBe('/analitica?tab=comparacion');
  });

  it('analyticsTabToUrl maps internal tabs to Spanish URL ids', () => {
    expect(analyticsTabToUrl('quality')).toBe('calidad');
    expect(analyticsTabToUrl('providers')).toBe('proveedores');
  });
});

describe('AnalyticsDashboardPage URL tabs', () => {
  it('normalizes missing tab to resumen in URL', async () => {
    renderAnalyticsAt('/analitica');
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=resumen');
    });
    expect(screen.getByRole('tab', { name: 'Resumen' })).toHaveAttribute('aria-selected', 'true');
  });

  it('opens Costos tab from ?tab=costos', async () => {
    renderAnalyticsAt('/analitica?tab=costos');
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Costos' })).toHaveAttribute('aria-selected', 'true');
    });
  });

  it('normalizes invalid tab to Resumen', async () => {
    renderAnalyticsAt('/analitica?tab=invalid-tab');
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('tab=resumen');
    });
    expect(screen.getByRole('tab', { name: 'Resumen' })).toHaveAttribute('aria-selected', 'true');
  });

  it('updates URL when clicking a tab and preserves filters', async () => {
    renderAnalyticsAt(
      '/analitica?tab=resumen&date_from=2026-01-01&date_to=2026-01-31&inventory_id=inv-1'
    );
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('inventory_id=inv-1'));
    fireEvent.click(screen.getByTestId('analytics-tab-aisles'));
    await waitFor(() => {
      const url = screen.getByTestId('location-probe').textContent ?? '';
      expect(url).toContain('tab=pasillos');
      expect(url).toContain('inventory_id=inv-1');
      expect(url).toContain('date_from=2026-01-01');
    });
  });
});

describe('AnalyticsDashboardPage URL filters', () => {
  it('initializes filter state from URL and passes filters to data hook', async () => {
    renderAnalyticsAt(
      '/analitica?tab=pasillos&date_from=2026-01-01&date_to=2026-01-31&inventory_id=inv-1&aisle_id=a-1'
    );
    await waitFor(() => expect(mockUseAnalyticsDashboardData).toHaveBeenCalled());
    const firstCall = mockUseAnalyticsDashboardData.mock.calls[0]?.[0] as {
      analytics: { inventory_id?: string; aisle_id?: string; date_from?: string };
    };
    expect(firstCall.analytics.inventory_id).toBe('inv-1');
    expect(firstCall.analytics.aisle_id).toBe('a-1');
    expect(firstCall.analytics.date_from).toBe('2026-01-01');
  });

  it('ignores aisle_id when inventory_id is missing', async () => {
    renderAnalyticsAt('/analitica?tab=pasillos&aisle_id=a-1');
    await waitFor(() => expect(mockUseAnalyticsDashboardData).toHaveBeenCalled());
    const firstCall = mockUseAnalyticsDashboardData.mock.calls[0]?.[0] as {
      analytics: { aisle_id?: string };
    };
    expect(firstCall.analytics.aisle_id).toBeUndefined();
  });

  it('writes filter params to URL when applying filters', async () => {
    renderAnalyticsAt('/analitica?tab=pasillos');
    await waitFor(() => expect(screen.getByTestId('analytics-apply-filters')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-01-31' } });
    fireEvent.click(screen.getByTestId('analytics-apply-filters'));
    await waitFor(() => {
      const url = screen.getByTestId('location-probe').textContent ?? '';
      expect(url).toContain('tab=pasillos');
      expect(url).toContain('date_from=2026-01-01');
      expect(url).toContain('date_to=2026-01-31');
    });
  });

  it('removes filter params on reset but keeps tab', async () => {
    renderAnalyticsAt(
      '/analitica?tab=costos&date_from=2026-01-01&date_to=2026-01-31&inventory_id=inv-1&provider_name=openai'
    );
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Costos' })).toHaveAttribute('aria-selected', 'true'));
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }));
    await waitFor(() => {
      const url = screen.getByTestId('location-probe').textContent ?? '';
      expect(url).toContain('tab=costos');
      expect(url).not.toContain('inventory_id=');
      expect(url).not.toContain('provider_name=');
      expect(url).not.toContain('date_from=2026-01-01');
    });
  });

  it('restores filters on browser back', async () => {
    const { router } = renderAnalyticsRouter(
      [
        '/analitica?tab=costos&inventory_id=inv-1',
        '/analitica?tab=costos&inventory_id=inv-2',
      ],
      1
    );
    await waitFor(() => {
      const lastCall = mockUseAnalyticsDashboardData.mock.calls.at(-1)?.[0] as {
        analytics: { inventory_id?: string };
      };
      expect(lastCall.analytics.inventory_id).toBe('inv-2');
    });
    await router.navigate(-1);
    await waitFor(() => {
      const lastCall = mockUseAnalyticsDashboardData.mock.calls.at(-1)?.[0] as {
        analytics: { inventory_id?: string };
      };
      expect(lastCall.analytics.inventory_id).toBe('inv-1');
    });
  });

  it('preserves unknown query params when applying filters', async () => {
    renderAnalyticsAt('/analitica?tab=pasillos&foo=bar');
    await waitFor(() => expect(screen.getByTestId('analytics-apply-filters')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-01-31' } });
    fireEvent.click(screen.getByTestId('analytics-apply-filters'));
    await waitFor(() => {
      const url = screen.getByTestId('location-probe').textContent ?? '';
      expect(url).toContain('foo=bar');
      expect(url).toContain('date_from=2026-01-01');
    });
  });

  it('falls back to default dates for invalid date params', async () => {
    renderAnalyticsAt('/analitica?tab=resumen&date_from=not-a-date&date_to=2026-13-40');
    await waitFor(() => expect(mockUseAnalyticsDashboardData).toHaveBeenCalled());
    const firstCall = mockUseAnalyticsDashboardData.mock.calls[0]?.[0] as {
      analytics: { date_from?: string; date_to?: string };
    };
    expect(firstCall.analytics.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(firstCall.analytics.date_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(firstCall.analytics.date_from).not.toBe('not-a-date');
    await waitFor(() => {
      const url = screen.getByTestId('location-probe').textContent ?? '';
      expect(url).not.toContain('not-a-date');
    });
  });
});

describe('legacy analytics redirects', () => {
  function renderLegacyRedirect(path: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/metrics" element={<MetricsLegacyRedirect />} />
            <Route path="/observabilidad" element={<ObservabilityLegacyRedirect />} />
            <Route
              path="/analitica"
              element={
                <>
                  <AnalyticsDashboardPage />
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it('redirects /metrics to /analitica?tab=calidad via MetricsLegacyRedirect', async () => {
    renderLegacyRedirect('/metrics');
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=calidad');
    });
  });

  it('redirects /observabilidad to /analitica?tab=proveedores via ObservabilityLegacyRedirect', async () => {
    renderLegacyRedirect('/observabilidad');
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=proveedores');
    });
  });
});
