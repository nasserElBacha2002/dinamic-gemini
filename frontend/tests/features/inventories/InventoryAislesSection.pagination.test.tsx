import '@testing-library/jest-dom/vitest';
import { createRef, type ChangeEvent, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('shows pagination controls when aisle list exceeds page size', async () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      makeRow(`aisle-${i + 1}`, `A-${String(i + 1).padStart(2, '0')}`)
    );
    render(
      <WithProviders>
        <InventoryAislesSection {...baseProps} tableRows={rows} filteredTableRows={rows} />
      </WithProviders>
    );

    expect(await screen.findByText('A-01')).toBeInTheDocument();
    expect(await screen.findByText('A-25')).toBeInTheDocument();
    expect(screen.queryByText('A-26')).not.toBeInTheDocument();

    const nextButton = await screen.findByRole('button', { name: /siguiente|next page/i });
    fireEvent.click(nextButton);

    await waitFor(() => {
      expect(screen.getByText('A-26')).toBeInTheDocument();
    });
    expect(screen.queryByText('A-01')).not.toBeInTheDocument();
  });

  it('resets to page 1 when search changes', async () => {
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

    const nextButton = await screen.findByRole('button', { name: /siguiente|next page/i });
    fireEvent.click(nextButton);
    await screen.findByText('A-26');

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

    expect(await screen.findByText('A-01')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('A-26')).not.toBeInTheDocument();
    });
  });

  it('resets to page 1 when a sortable column header is clicked', async () => {
    const rows = Array.from({ length: 30 }, (_, i) =>
      makeRow(`aisle-${i + 1}`, `A-${String(i + 1).padStart(2, '0')}`)
    );
    render(
      <WithProviders>
        <InventoryAislesSection {...baseProps} tableRows={rows} filteredTableRows={rows} />
      </WithProviders>
    );

    const nextButton = await screen.findByRole('button', { name: /siguiente|next page/i });
    fireEvent.click(nextButton);
    await screen.findByText('A-26');
    expect(screen.queryByText('A-01')).not.toBeInTheDocument();

    const sortButton = await screen.findByRole('button', { name: /aisle\.code_label/i });
    fireEvent.click(sortButton);

    expect(await screen.findByText('A-01')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('A-26')).not.toBeInTheDocument();
    });
  });
});
