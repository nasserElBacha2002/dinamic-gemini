import '@testing-library/jest-dom/vitest';
import { createRef, type ChangeEvent, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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

function makeTxtRow(): AisleInventoryTableRow {
  return {
    presentation: {
      id: 'aisle-txt',
      code: 'P5',
      isActive: true,
      clientSupplierId: 'sup-1',
      clientSupplierName: 'etiqueta-interna',
      aisleStatusLabel: 'aisle.scanner_txt_import_badge',
      aisleStatusSemantic: 'info',
      assetsCount: 0,
      assetsCountDisplay: 'aisle.scanner_txt_assets_display',
      positionsCount: 5,
      positionsCountDisplay: '5',
      pendingReviewCount: 0,
      pendingReviewDisplay: '0',
      lastUpdatedSortKey: '2026-08-28T00:00:00Z',
      lastUpdatedDisplay: '28/8/2026',
      latestRun: null,
      referenceUsage: null,
      isScannerTxtImport: true,
    },
    action: {
      processMenuAisle: {
        id: 'aisle-txt',
        status: 'processed',
        assets_count: 0,
        has_dinamic_scanner_txt_import: true,
      },
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

describe('InventoryAislesSection scanner TXT import', () => {
  it('hides the process action for TXT-imported aisles', () => {
    const row = makeTxtRow();
    render(
      <WithProviders>
        <InventoryAislesSection {...baseProps} tableRows={[row]} filteredTableRows={[row]} />
      </WithProviders>
    );

    expect(screen.queryByTestId('aisle-action-process-aisle-txt')).not.toBeInTheDocument();
    expect(screen.getByText('aisle.scanner_txt_import_badge')).toBeInTheDocument();
  });
});
