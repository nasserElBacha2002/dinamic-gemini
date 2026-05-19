import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnalyticsMetricCard } from '../src/features/analytics-dashboard/components/base/AnalyticsMetricCard';

describe('AnalyticsMetricCard', () => {
  it('renders compact variant', () => {
    render(<AnalyticsMetricCard label="Costo" value="12 €" size="compact" testId="metric-compact" />);
    expect(screen.getByTestId('metric-compact')).toBeInTheDocument();
    expect(screen.getByText('Costo')).toBeInTheDocument();
    expect(screen.getByText('12 €')).toBeInTheDocument();
  });

  it('renders regular variant', () => {
    render(<AnalyticsMetricCard label="Pendientes" value={42} size="regular" testId="metric-regular" />);
    expect(screen.getByTestId('metric-regular')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('renders hero variant', () => {
    render(<AnalyticsMetricCard label="Total" value="99 %" size="hero" testId="metric-hero" />);
    expect(screen.getByTestId('metric-hero')).toBeInTheDocument();
    expect(screen.getByText('99 %')).toBeInTheDocument();
  });
});
