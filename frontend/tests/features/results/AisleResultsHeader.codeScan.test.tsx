import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AisleResultsHeader from '../../../src/features/results/components/AisleResultsHeader';

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

describe('AisleResultsHeader code scan menu', () => {
  it('opens code scan from Más acciones menu', () => {
    const onOpenCodeScan = vi.fn();
    render(
      <MemoryRouter>
        <AisleResultsHeader {...baseProps} onOpenCodeScan={onOpenCodeScan} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('aisle-code-scan-open')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    fireEvent.click(screen.getByTestId('aisle-code-scan-menu-open'));
    expect(onOpenCodeScan).toHaveBeenCalledTimes(1);
  });

  it('opens observability from Más acciones menu', () => {
    const onOpenObservability = vi.fn();
    render(
      <MemoryRouter>
        <AisleResultsHeader {...baseProps} onOpenObservability={onOpenObservability} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('aisle-results-more-actions'));
    fireEvent.click(screen.getByTestId('aisle-observability-menu-open'));
    expect(onOpenObservability).toHaveBeenCalledTimes(1);
  });
});
