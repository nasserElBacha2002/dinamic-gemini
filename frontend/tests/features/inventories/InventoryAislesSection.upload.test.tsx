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
  onOpenCreateAisle: vi.fn(),
};

describe('InventoryAislesSection upload buttons', () => {
  it('disables all upload buttons while any aisle is uploading', () => {
    const rows = [makeRow('aisle-a', 'A-1'), makeRow('aisle-b', 'B-1')];
    render(
      <WithProviders>
        <InventoryAislesSection
          {...baseProps}
          tableRows={rows}
          filteredTableRows={rows}
          uploadingAisleId="aisle-a"
        />
      </WithProviders>
    );

    expect(screen.getByTestId('aisle-action-upload-aisle-a')).toBeDisabled();
    expect(screen.getByTestId('aisle-action-upload-aisle-b')).toBeDisabled();
    expect(screen.getByTestId('aisle-action-upload-aisle-a')).toHaveTextContent('uploads.photos.uploadingButton');
    expect(screen.getByTestId('aisle-action-upload-aisle-b')).toHaveTextContent('aisle.upload_assets');
  });
});
