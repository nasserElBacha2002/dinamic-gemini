import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AisleResultsHeader from '../src/features/results/components/AisleResultsHeader';

const baseProps = {
  breadcrumbs: [{ label: 'Inventarios', to: '/' }],
  title: 'A-01',
  subtitle: 'Inventario test',
  mergeButtonVisible: false,
  mergeDisabledReason: '',
  mergeButtonDisabled: true,
  isMerging: false,
  onRunMerge: vi.fn(),
  showCompareRuns: false,
  onCompareRuns: vi.fn(),
  showCompareOperational: false,
  onCompareOperational: vi.fn(),
  showPromoteRun: false,
  onPromoteRun: vi.fn(),
  exportDisabled: false,
  exportingCsv: false,
  onExport: vi.fn(),
  refreshDisabled: false,
  onRefresh: vi.fn(),
};

describe('AisleActiveStateActions', () => {
  it('shows inactive badge when showInactiveBadge is true', () => {
    render(
      <MemoryRouter>
        <AisleResultsHeader {...baseProps} showInactiveBadge />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('aisle-inactive-badge')).toBeInTheDocument();
    expect(screen.getByText(/inactivo|inactive/i)).toBeInTheDocument();
  });

  it('opens deactivate from Más acciones menu', () => {
    const onDeactivate = vi.fn();
    render(
      <MemoryRouter>
        <AisleResultsHeader {...baseProps} onDeactivate={onDeactivate} onEditName={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    fireEvent.click(screen.getByTestId('aisle-deactivate'));
    expect(onDeactivate).toHaveBeenCalledTimes(1);
  });

  it('shows reactivate when onReactivate is provided', () => {
    const onReactivate = vi.fn();
    render(
      <MemoryRouter>
        <AisleResultsHeader
          {...baseProps}
          showInactiveBadge
          onReactivate={onReactivate}
          onEditName={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    expect(screen.queryByTestId('aisle-deactivate')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('aisle-reactivate'));
    expect(onReactivate).toHaveBeenCalledTimes(1);
  });
});

describe('aisle inactive copy', () => {
  it('exposes Spanish deactivate body about quantities vs costs', async () => {
    const i18n = (await import('../src/i18n')).default;
    await i18n.loadLanguages('es');
    const body = i18n.t('aisle.deactivate_body', { lng: 'es' });
    expect(body).toMatch(/cantidades/i);
    expect(body).toMatch(/costos/i);
    expect(body).toMatch(/resumen|exportaciones/i);
    const note = i18n.t('aisle.inactive_historical_note', { lng: 'es' });
    expect(note).toMatch(/históric/i);
    expect(note).toMatch(/totales operativos/i);
  });
});
