import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import AnalyticsDashboardPage from '../src/features/analytics-dashboard/AnalyticsDashboardPage';
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
          <Route path="/metrics" element={<AnalyticsDashboardPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
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

  it('updates URL when clicking a tab', async () => {
    renderAnalyticsAt('/analitica?tab=resumen');
    await waitFor(() => expect(screen.getByTestId('location-probe')).toHaveTextContent('tab=resumen'));
    fireEvent.click(screen.getByTestId('analytics-tab-quality'));
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('tab=calidad');
    });
  });
});

describe('legacy analytics redirects', () => {
  it('redirects /metrics to /analitica?tab=calidad', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/metrics']}>
          <Routes>
            <Route path="/metrics" element={<Navigate to={pathToAnalytics('quality')} replace />} />
            <Route path="/analitica" element={<AnalyticsDashboardPage />} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=calidad');
    });
  });
});
