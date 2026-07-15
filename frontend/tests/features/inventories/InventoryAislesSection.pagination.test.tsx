import '@testing-library/jest-dom/vitest';
import { createRef, type ChangeEvent, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import theme from '../../../src/theme';
import type { AisleInventoryTableRow } from '../../../src/features/inventories/adapters';
import InventoryAislesSection from '../../../src/features/inventories/components/InventoryAislesSection';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

function WithProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <MemoryRouter>{children}</MemoryRouter>
    </ThemeProvider>
  );
}

function makeRow(id: string, code: string): AisleInventoryTableRow {
  return {
    presentation: {
      id,
      code,
      isActive: true,
      clientSupplierId: null,
      aisleStatusLabel: 'Draft',
      aisleStatusSemantic: 'neutral',
      assetsCount: 0,
      assetsCountDisplay: '0',
      positionsCount: 0,
      positionsCountDisplay: '0',
      pendingReviewCount: 0,
      pendingReviewDisplay: '0',
      lastUpdatedSortKey: null,
      lastUpdatedDisplay: '—',
      latestRun: null,
      referenceUsage: null,
    },
    action: {
      processMenuAisle: { id, status: 'draft', assets_count: 0 },
      observabilityInitialRunId: null,
    },
  };
}

const baseProps = {
  inventoryId: 'inv-1',
  aislesLoading: false,
  aisleTableSearch: '',
  onAisleTableSearch: vi.fn(),
  onRefreshAisles: vi.fn(),
  fileInputRef: createRef<HTMLInputElement>(),
  onFileInputChange: vi.fn() as (e: ChangeEvent<HTMLInputElement>) => void,
  onRequestUpload: vi.fn(),
  onRequestProcess: vi.fn(),
  aislesDataLoaded: true,
  processingAisleId: null as string | null,
  uploadingAisleId: null as string | null,
  onOpenCreateAisle: vi.fn(),
};

describe('InventoryAislesSection pagination', () => {
  it('shows pagination controls when aisle list exceeds page size', () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      makeRow(`aisle-${i + 1}`, `A-${String(i + 1).padStart(2, '0')}`)
    );
    render(
      <WithProviders>
        <InventoryAislesSection {...baseProps} tableRows={rows} filteredTableRows={rows} />
      </WithProviders>
    );

    expect(screen.getByText('A-01')).toBeInTheDocument();
    expect(screen.getByText('A-25')).toBeInTheDocument();
    expect(screen.queryByText('A-26')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('A-26')).toBeInTheDocument();
    expect(screen.queryByText('A-01')).not.toBeInTheDocument();
  });

  it('resets to page 1 when search changes', () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      makeRow(`aisle-${i + 1}`, `A-${String(i + 1).padStart(2, '0')}`)
    );
    const onAisleTableSearch = vi.fn();
    const { rerender } = render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          tableRows={rows}
          filteredTableRows={rows}
          onAisleTableSearch={onAisleTableSearch}
        />
      </WithProviders>
    );

    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('A-26')).toBeInTheDocument();

    rerender(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          tableRows={rows}
          filteredTableRows={rows.slice(0, 5)}
          aisleTableSearch="A-0"
          onAisleTableSearch={onAisleTableSearch}
        />
      </WithProviders>
    );

    expect(screen.getByText('A-01')).toBeInTheDocument();
    expect(screen.queryByText('A-26')).not.toBeInTheDocument();
  });

  it('resets to page 1 when a sortable column header is clicked', () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      makeRow(`aisle-${i + 1}`, `A-${String(i + 1).padStart(2, '0')}`)
    );
    render(
      <WithProviders>
        <InventoryAislesSection {...baseProps} tableRows={rows} filteredTableRows={rows} />
      </WithProviders>
    );

    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('A-26')).toBeInTheDocument();
    expect(screen.queryByText('A-01')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /aisle\.code_label/i }));
    expect(screen.getByText('A-01')).toBeInTheDocument();
    expect(screen.queryByText('A-26')).not.toBeInTheDocument();
  });
});
