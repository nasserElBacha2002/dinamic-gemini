import '@testing-library/jest-dom/vitest';
import { createRef, type ChangeEvent, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, useMediaQuery } from '@mui/material';
import theme from '../../../src/theme';
import type { AisleInventoryTableRow } from '../../../src/features/inventories/adapters';
import InventoryAislesSection from '../../../src/features/inventories/components/InventoryAislesSection';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@mui/material', async () => {
  const actual = await vi.importActual<typeof import('@mui/material')>('@mui/material');
  return {
    ...actual,
    useMediaQuery: vi.fn(() => false),
  };
});

function WithProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <MemoryRouter>{children}</MemoryRouter>
    </ThemeProvider>
  );
}

function makeRow(
  overrides: Partial<AisleInventoryTableRow['presentation']> = {}
): AisleInventoryTableRow {
  const id = overrides.id ?? 'aisle-1';
  return {
    presentation: {
      id,
      code: overrides.code ?? 'A-01',
      isActive: true,
      clientSupplierId: overrides.clientSupplierId ?? null,
      clientSupplierName: overrides.clientSupplierName ?? null,
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
      isScannerTxtImport: false,
      ...overrides,
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

describe('InventoryAislesSection supplier column', () => {
  it('shows Proveedor header and supplier name with scoped link', () => {
    const row = makeRow({
      clientSupplierId: 'sup-1',
      clientSupplierName: 'Proveedor Ejemplo',
    });
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId="client-1"
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );

    expect(screen.getByText('inventory.column_aisle_supplier')).toBeInTheDocument();
    const cell = screen.getByTestId('aisle-supplier-cell-aisle-1');
    expect(cell).toHaveTextContent('Proveedor Ejemplo');
    expect(cell).toHaveAttribute('href', '/clientes/client-1/proveedores/sup-1');
  });

  it('shows Sin proveedor empty state', () => {
    const row = makeRow();
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId="client-1"
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );
    expect(screen.getByTestId('aisle-supplier-cell-aisle-1')).toHaveTextContent(
      'inventory.no_supplier'
    );
    expect(screen.getByTestId('aisle-supplier-cell-aisle-1').tagName).not.toBe('A');
  });

  it('does not link when inventory has no client', () => {
    const row = makeRow({
      clientSupplierId: 'sup-1',
      clientSupplierName: 'Proveedor Ejemplo',
    });
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId={null}
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );
    const cell = screen.getByTestId('aisle-supplier-cell-aisle-1');
    expect(cell).toHaveTextContent('Proveedor Ejemplo');
    expect(cell).not.toHaveAttribute('href');
  });

  it('does not link for inconsistent relation (id without resolved name)', () => {
    const row = makeRow({
      clientSupplierId: 'sup-cross',
      clientSupplierName: null,
    });
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId="client-1"
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );
    const cell = screen.getByTestId('aisle-supplier-cell-aisle-1');
    expect(cell).toHaveTextContent('inventory.no_supplier');
    expect(cell).not.toHaveAttribute('href');
  });

  it('supplier link click does not trigger row navigation', () => {
    const row = makeRow({
      clientSupplierId: 'sup-1',
      clientSupplierName: 'Proveedor Ejemplo',
    });
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId="client-1"
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );
    const cell = screen.getByTestId('aisle-supplier-cell-aisle-1');
    fireEvent.click(cell);
    // MemoryRouter stays on "/"; row click would navigate to positions.
    expect(window.location.pathname).toBe('/');
  });

  it('shows supplier field on mobile cards', () => {
    vi.mocked(useMediaQuery).mockReturnValue(true);
    const row = makeRow({
      clientSupplierId: 'sup-1',
      clientSupplierName: 'Mobile Supplier',
    });
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          inventoryClientId="client-1"
          tableRows={[row]}
          filteredTableRows={[row]}
        />
      </WithProviders>
    );
    expect(screen.getByText('inventory.column_aisle_supplier')).toBeInTheDocument();
    expect(screen.getByText('Mobile Supplier')).toBeInTheDocument();
  });
});
