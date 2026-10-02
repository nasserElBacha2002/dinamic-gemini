import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DinamicScannerTxtImportResponse } from '../src/api/types';
import ImportLocalInventoryPackageDialog from '../src/features/inventories/components/ImportLocalInventoryPackageDialog';

const { confirmTxtMock, previewTxtMock, useClientSuppliersMock } = vi.hoisted(() => ({
  confirmTxtMock: vi.fn(),
  previewTxtMock: vi.fn(),
  useClientSuppliersMock: vi.fn(),
}));

vi.mock('../src/api/dinamicScannerTxtImportsApi', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../src/api/dinamicScannerTxtImportsApi')
  >();
  return {
    ...actual,
    confirmDinamicScannerTxtImport: confirmTxtMock,
    previewDinamicScannerTxtImport: previewTxtMock,
  };
});

vi.mock('../src/hooks/useClients', () => ({
  useClientSuppliers: useClientSuppliersMock,
}));

const preview: DinamicScannerTxtImportResponse = {
  aisle_code: 'P1',
  aisle_id: '',
  aisle_created: false,
  aisle_will_be_created: true,
  positions_imported: 4,
  products_imported: 11,
  omitted_records: 2,
  parse_warnings: ['line 5: duplicate_unique_label_id'],
  duplicate: false,
  csv_import: {
    import_id: 'import-1',
    export_id: 'scanner-txt-1',
    status: 'PREVIEWED',
    total_rows: 11,
    valid_rows: 11,
    rejected_rows: 0,
    duplicate_rows: 2,
    rows: [],
  },
};

describe('ImportLocalInventoryPackageDialog scanner TXT supplier selection', () => {
  beforeEach(() => {
    previewTxtMock.mockReset();
    confirmTxtMock.mockReset();
    previewTxtMock.mockResolvedValue(preview);
    confirmTxtMock.mockResolvedValue({
      ...preview,
      aisle_id: 'aisle-p1',
      aisle_created: true,
    });
    useClientSuppliersMock.mockReturnValue({
      data: {
        items: [
          { id: 'supplier-1', name: 'Supplier One' },
          { id: 'supplier-2', name: 'Supplier Two' },
        ],
      },
      isLoading: false,
      isError: false,
    });
  });

  it('sends the selected client supplier when confirming a new P1 aisle', async () => {
    render(
      <ImportLocalInventoryPackageDialog
        open
        inventoryId="inventory-1"
        inventoryClientId="client-1"
        onClose={vi.fn()}
      />
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['POSITION|POS1|01|RIGHT'], 'P1.txt', { type: 'text/plain' })] },
    });
    fireEvent.click(screen.getByTestId('import-package-preview'));

    const supplierSelect = await screen.findByRole('combobox', {
      name: /proveedor del pasillo|aisle supplier/i,
    });
    fireEvent.mouseDown(supplierSelect);
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByText('Supplier Two'));
    fireEvent.click(screen.getByTestId('import-package-confirm'));

    await waitFor(() => {
      expect(confirmTxtMock).toHaveBeenCalledWith('inventory-1', {
        export_id: 'scanner-txt-1',
        conflict_policy: 'SKIP',
        client_supplier_id: 'supplier-2',
      });
    });
  });
});
