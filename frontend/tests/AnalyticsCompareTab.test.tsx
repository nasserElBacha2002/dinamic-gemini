import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnalyticsCompareTab } from '../src/features/analytics-dashboard/components/AnalyticsCompareTab';

const mockNavigate = vi.fn();
const workspaceMock = vi.fn((props: {
  mode: string;
  inventoryId: string;
  initialAisleId?: string;
  onNavigateToStandalone?: (href: string) => void;
}) => (
  <div
    data-testid="compare-many-workspace-mock"
    data-mode={props.mode}
    data-inventory-id={props.inventoryId}
    data-initial-aisle-id={props.initialAisleId ?? ''}
  />
));

vi.mock('../src/features/analytics/compare/CompareManyRunsWorkspace', () => ({
  CompareManyRunsWorkspace: (props: unknown) => workspaceMock(props as never),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderTab(props: React.ComponentProps<typeof AnalyticsCompareTab>) {
  return render(
    <MemoryRouter>
      <AnalyticsCompareTab {...props} />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  workspaceMock.mockClear();
});

describe('AnalyticsCompareTab', () => {
  it('shows select inventory hint when no inventory selected', () => {
    renderTab({ inventoryId: '', aisleId: '', inventoryName: null, processingMode: undefined });
    expect(screen.getByText(/Seleccioná un inventario/i)).toBeInTheDocument();
    expect(screen.queryByTestId('compare-many-workspace-mock')).not.toBeInTheDocument();
  });

  it('shows unavailable warning for non-test inventory', () => {
    renderTab({
      inventoryId: 'inv-prod',
      aisleId: '',
      inventoryName: 'Prod DC',
      processingMode: 'production',
    });
    expect(screen.getByTestId('analytics-compare-unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('compare-many-workspace-mock')).not.toBeInTheDocument();
  });

  it('embeds compare workspace for eligible test inventory', () => {
    renderTab({
      inventoryId: 'inv-test',
      aisleId: '',
      inventoryName: 'Test DC',
      processingMode: 'test',
    });
    expect(screen.getByTestId('compare-many-workspace-mock')).toBeInTheDocument();
    expect(workspaceMock).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'embedded',
        inventoryId: 'inv-test',
      })
    );
  });

  it('passes initial aisle id to workspace', () => {
    renderTab({
      inventoryId: 'inv-test',
      aisleId: 'a-1',
      inventoryName: 'Test DC',
      processingMode: 'test',
    });
    const el = screen.getByTestId('compare-many-workspace-mock');
    expect(el).toHaveAttribute('data-initial-aisle-id', 'a-1');
  });

  it('navigates to href provided by workspace standalone callback', () => {
    renderTab({
      inventoryId: 'inv-test',
      aisleId: 'a-1',
      inventoryName: 'Test DC',
      processingMode: 'test',
    });
    const props = workspaceMock.mock.calls[0]?.[0];
    const href =
      '/inventories/inv-test/analytics/compare-many?aisleId=a-1&jobIds=j1%2Cj2&baseline=j1';
    props?.onNavigateToStandalone?.(href);
    expect(mockNavigate).toHaveBeenCalledWith(href);
  });
});
