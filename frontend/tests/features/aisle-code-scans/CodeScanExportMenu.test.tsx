import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CodeScanExportMenu from '../../../src/features/aisle-code-scans/components/CodeScanExportMenu';

const exportAisleCodeScansCsv = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const showSnackbar = vi.hoisted(() => vi.fn());

vi.mock('../../../src/api/codeScansApi', () => ({
  exportAisleCodeScansCsv,
}));

vi.mock('../../../src/components/ui', () => ({
  useAppSnackbar: () => ({ showSnackbar, closeSnackbar: vi.fn() }),
}));

describe('CodeScanExportMenu', () => {
  beforeEach(() => {
    exportAisleCodeScansCsv.mockClear();
    showSnackbar.mockClear();
  });

  it('renders export button and menu options', () => {
    render(<CodeScanExportMenu inventoryId="inv-1" aisleId="aisle-1" />);
    fireEvent.click(screen.getByTestId('code-scan-export-button'));
    expect(screen.getByText('Exportar detecciones')).toBeInTheDocument();
    expect(screen.getByText('Exportar códigos sin coincidencia')).toBeInTheDocument();
    expect(screen.getByText('Exportar resumen')).toBeInTheDocument();
  });

  it('calls export endpoint for detections', async () => {
    render(<CodeScanExportMenu inventoryId="inv-1" aisleId="aisle-1" />);
    fireEvent.click(screen.getByTestId('code-scan-export-button'));
    fireEvent.click(screen.getByText('Exportar detecciones'));
    await vi.waitFor(() => {
      expect(exportAisleCodeScansCsv).toHaveBeenCalledWith('inv-1', 'aisle-1', 'detections');
    });
  });
});
