import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnalyticsEntityRankingCards } from '../src/features/analytics-dashboard/components/rankings/AnalyticsEntityRankingCards';

describe('AnalyticsEntityRankingCards', () => {
  it('renders title, subtitle, metadata and actions', () => {
    render(
      <MemoryRouter>
        <AnalyticsEntityRankingCards
          testId="ranking"
          emptyText="Sin datos"
          items={[
            {
              id: 'inv-1',
              title: 'Inventario Norte',
              subtitle: 'Alta actividad',
              metadata: [{ id: 'cost', label: 'Costo total', value: '10 €' }],
              actions: [{ id: 'detail', label: 'Ver detalle', href: '/inventarios/inv-1', testId: 'rank-detail' }],
              testId: 'rank-card-inv-1',
            },
          ]}
        />
      </MemoryRouter>
    );
    expect(screen.getByTestId('ranking')).toBeInTheDocument();
    expect(screen.getByText('Inventario Norte')).toBeInTheDocument();
    expect(screen.getByText('Alta actividad')).toBeInTheDocument();
    expect(screen.getByText(/Costo total/)).toBeInTheDocument();
    expect(screen.getByTestId('rank-detail')).toBeInTheDocument();
  });

  it('renders shared empty text when there are no items', () => {
    render(<AnalyticsEntityRankingCards testId="ranking" emptyText="Sin pasillos" items={[]} />);
    expect(screen.getByTestId('ranking-empty')).toHaveTextContent('Sin pasillos');
  });
});
