import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import InventoryExportMenu from '../src/features/inventories/components/InventoryExportMenu';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      (
        {
          'inventory.export_menu': 'Exportar',
          'inventory.export_summary': 'Resumen del inventario',
          'inventory.export_package_zip': 'Inventario completo (.zip)',
          'common.exporting': 'Exportando',
        } as Record<string, string>
      )[key] ?? key,
  }),
}));

const { exportInventorySummaryCsv, exportInventoryPackageZip } = vi.hoisted(() => ({
  exportInventorySummaryCsv: vi.fn().mockResolvedValue(undefined),
  exportInventoryPackageZip: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../src/api/client', () => ({
  exportInventorySummaryCsv,
  exportInventoryPackageZip,
}));

vi.mock('../src/components/ui', () => ({
  useAppSnackbar: () => ({ showSnackbar: vi.fn() }),
}));

describe('InventoryExportMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows Exportar menu label not legacy aisle export copy', () => {
    render(<InventoryExportMenu inventoryId="inv-1" />);
    expect(screen.getByTestId('inventory-export-menu')).toHaveTextContent('Exportar');
    expect(screen.getByTestId('inventory-export-menu')).not.toHaveTextContent(
      'Exportar CSV del pasillo'
    );
  });

  it('shows export menu with summary and package options', () => {
    render(<InventoryExportMenu inventoryId="inv-1" />);
    fireEvent.click(screen.getByTestId('inventory-export-menu'));
    expect(screen.getByTestId('inventory-export-summary')).toHaveTextContent('Resumen del inventario');
    expect(screen.getByTestId('inventory-export-package')).toHaveTextContent('Inventario completo (.zip)');
  });

  it('calls summary export when summary menu item clicked', async () => {
    render(<InventoryExportMenu inventoryId="inv-1" />);
    fireEvent.click(screen.getByTestId('inventory-export-menu'));
    fireEvent.click(screen.getByTestId('inventory-export-summary'));
    expect(exportInventorySummaryCsv).toHaveBeenCalledWith('inv-1');
  });

  it('calls package export when package menu item clicked', async () => {
    render(<InventoryExportMenu inventoryId="inv-1" />);
    fireEvent.click(screen.getByTestId('inventory-export-menu'));
    fireEvent.click(screen.getByTestId('inventory-export-package'));
    expect(exportInventoryPackageZip).toHaveBeenCalledWith('inv-1');
  });
});
