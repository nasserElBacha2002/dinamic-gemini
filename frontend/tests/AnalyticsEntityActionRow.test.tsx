import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnalyticsEntityActionRow } from '../src/features/analytics-dashboard/components/actions/AnalyticsEntityActionRow';

describe('AnalyticsEntityActionRow', () => {
  it('renders href action as router link', () => {
    render(
      <MemoryRouter>
        <AnalyticsEntityActionRow
          actions={[{ id: 'detail', label: 'Ver detalle', href: '/inventarios/inv-1', testId: 'action-detail' }]}
        />
      </MemoryRouter>
    );
    const link = screen.getByTestId('action-detail');
    expect(link).toHaveAttribute('href', '/inventarios/inv-1');
  });

  it('renders onClick action as button link', () => {
    const onClick = vi.fn();
    render(
      <AnalyticsEntityActionRow
        actions={[{ id: 'analytics', label: 'Ver en analítica', onClick, testId: 'action-analytics' }]}
      />
    );
    fireEvent.click(screen.getByTestId('action-analytics'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('renders disabled action with tooltip', () => {
    render(
      <AnalyticsEntityActionRow
        actions={[
          {
            id: 'compare',
            label: 'Comparar corridas',
            disabled: true,
            tooltip: 'Solo inventarios de prueba',
            testId: 'action-compare-disabled',
          },
        ]}
      />
    );
    expect(screen.getByTestId('action-compare-disabled')).toHaveTextContent('Comparar corridas');
  });

  it('does not render disabled action without tooltip', () => {
    render(
      <AnalyticsEntityActionRow
        actions={[{ id: 'compare', label: 'Comparar corridas', disabled: true, testId: 'action-compare-hidden' }]}
      />
    );
    expect(screen.queryByTestId('action-compare-hidden')).not.toBeInTheDocument();
  });
});
