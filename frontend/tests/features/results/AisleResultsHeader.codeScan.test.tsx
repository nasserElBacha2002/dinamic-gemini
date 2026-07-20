/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../src/i18n';
import AisleResultsHeader from '../../../src/features/results/components/AisleResultsHeader';

const baseProps = {
  breadcrumbs: [{ label: 'Inv', to: '/' }],
  title: 'A01',
  subtitle: null,
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

function wrap(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </MemoryRouter>
  );
}

describe('AisleResultsHeader more actions (Phase 8)', () => {
  it('does not expose Escanear códigos (CODE_SCAN lives in Procesar)', () => {
    wrap(<AisleResultsHeader {...baseProps} onOpenObservability={vi.fn()} />);
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    expect(screen.queryByTestId('aisle-code-scan-menu-open')).not.toBeInTheDocument();
    expect(screen.queryByText(/Escanear códigos|Scan codes/i)).not.toBeInTheDocument();
  });

  it('still exposes observability from more actions', () => {
    const onOpenObservability = vi.fn();
    wrap(<AisleResultsHeader {...baseProps} onOpenObservability={onOpenObservability} />);
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    fireEvent.click(screen.getByTestId('aisle-observability-menu-open'));
    expect(onOpenObservability).toHaveBeenCalledTimes(1);
  });

  it('menu still renders export', () => {
    wrap(<AisleResultsHeader {...baseProps} />);
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    const menu = screen.getByRole('menu');
    expect(within(menu).getByTestId('aisle-export-operational')).toBeInTheDocument();
  });
});
