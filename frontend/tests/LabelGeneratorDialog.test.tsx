import '@testing-library/jest-dom/vitest';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ClientSupplier } from '../src/api/types';
import LabelGeneratorDialog from '../src/features/clients/components/LabelGeneratorDialog';
import { LABEL_PRINT_TITLE } from '../src/features/clients/components/labelPrintUtils';

const suppliers: ClientSupplier[] = [
  {
    id: 'supplier-1',
    client_id: 'client-1',
    name: 'Proveedor Rabbione',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
];

function renderDialog(overrides: Partial<ComponentProps<typeof LabelGeneratorDialog>> = {}) {
  const onClose = vi.fn();
  const view = render(
    <LabelGeneratorDialog
      open
      onClose={onClose}
      clientId="client-1"
      clientName="Cliente Blainstein"
      suppliers={suppliers}
      {...overrides}
    />
  );
  return { onClose, ...view };
}

function getPrintRoot(): Element | null {
  return document.querySelector('.label-print-only-root');
}

function getPreviewSheet(): HTMLElement {
  return screen.getByTestId('label-preview-sheet');
}

function fillRequiredFields() {
  fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
    target: { value: '1931038' },
  });
  fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
    target: { value: '03' },
  });
}

describe('LabelGeneratorDialog', () => {
  beforeEach(() => {
    vi.spyOn(window, 'print').mockImplementation(() => {});
  });

  it('renders Spanish dialog title and prefilled client', () => {
    renderDialog();
    expect(screen.getByRole('dialog', { name: /generar etiquetas/i })).toBeInTheDocument();
    expect(screen.getByDisplayValue('Cliente Blainstein')).toBeInTheDocument();
    expect(screen.getByText(/las etiquetas no se guardan/i)).toBeInTheDocument();
  });

  it('lists suppliers in the dropdown', () => {
    renderDialog();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /proveedor/i }));
    expect(screen.getByRole('option', { name: /proveedor rabbione/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /sin proveedor/i })).toBeInTheDocument();
  });

  it('renders horizontal label card and warehouse title in preview', () => {
    renderDialog();
    fillRequiredFields();
    const preview = getPreviewSheet();
    const card = within(preview).getByTestId('label-card');
    expect(card).toHaveClass('label-card--horizontal');
    expect(within(preview).getByText(LABEL_PRINT_TITLE)).toBeInTheDocument();
  });

  it('renders CÓDIGO: and CANT. TOTAL: as primary labels instead of COD/CANTIDAD', () => {
    renderDialog();
    fillRequiredFields();
    const preview = getPreviewSheet();
    expect(within(preview).getByText('CÓDIGO:')).toBeInTheDocument();
    expect(within(preview).getByText('CANT. TOTAL:')).toBeInTheDocument();
    expect(within(preview).queryByText('CÓDIGO INTERNO')).not.toBeInTheDocument();
    expect(within(preview).queryByText(/^COD:/)).not.toBeInTheDocument();
    expect(within(preview).queryByText(/^CANTIDAD:/)).not.toBeInTheDocument();
  });

  it('shows long internal code complete without ellipsis in stacked primary rows', () => {
    renderDialog();
    const longCode = 'etetetetetetetetetetetetetet';
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: longCode },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '1212' },
    });

    const preview = getPreviewSheet();
    expect(within(preview).getByText(longCode)).toBeInTheDocument();
    expect(within(preview).queryByText(/\.\.\./)).not.toBeInTheDocument();

    const codeValue = within(preview).getByText(longCode);
    expect(codeValue).toHaveClass('label-code-main-value');
    expect(codeValue).not.toHaveClass('label-row-value');

    const quantityValue = within(preview).getByText('1212');
    expect(quantityValue).toHaveClass('label-quantity-value');
    expect(codeValue.closest('.label-primary-row')).not.toBe(quantityValue.closest('.label-primary-row'));
  });

  it('updates preview when Contado por is filled', () => {
    renderDialog();
    fillRequiredFields();
    fireEvent.change(screen.getByRole('textbox', { name: /contado por/i }), {
      target: { value: 'Ana López' },
    });
    const preview = getPreviewSheet();
    expect(within(preview).getByText('CONTADO POR:')).toBeInTheDocument();
    expect(within(preview).getByText('Ana López')).toBeInTheDocument();
  });

  it('omits empty optional fields from the label', () => {
    renderDialog();
    fillRequiredFields();
    const preview = getPreviewSheet();
    expect(within(preview).queryByText('LOTE:')).not.toBeInTheDocument();
    expect(within(preview).queryByText('CONTADO POR:')).not.toBeInTheDocument();
    expect(within(preview).queryByText('PROVEEDOR:')).not.toBeInTheDocument();
  });

  it('uses single-label horizontal grid for one copy in preview', () => {
    renderDialog();
    fillRequiredFields();
    const preview = getPreviewSheet();
    const grid = within(preview).getByTestId('label-print-grid');
    expect(grid).toHaveClass('label-print-grid--horizontal');
    expect(grid).toHaveClass('single-label');
    expect(grid).toHaveAttribute('data-layout', 'single');
    expect(within(preview).getAllByTestId('label-card')).toHaveLength(1);
  });

  it('renders exactly one print-only label card for a single copy', () => {
    renderDialog();
    fillRequiredFields();
    const printRoot = getPrintRoot();
    expect(printRoot).toBeTruthy();
    expect(printRoot?.parentElement).toBe(document.body);
    expect(printRoot?.querySelectorAll('.label-card')).toHaveLength(1);
    expect(printRoot?.querySelector('[data-copies="1"]')).toBeTruthy();
    expect(document.querySelector('.label-preview-root .label-print-root')).toBeFalsy();
  });

  it('renders three print-only label cards when copies is 3', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'X1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '1' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: /^copias$/i }), {
      target: { value: '3' },
    });
    const printRoot = getPrintRoot();
    expect(printRoot?.querySelectorAll('.label-card')).toHaveLength(3);
    expect(printRoot?.querySelector('[data-copies="3"]')).toBeTruthy();
  });

  it('renders exactly one QR in preview label card', () => {
    renderDialog();
    fillRequiredFields();
    const card = within(getPreviewSheet()).getByTestId('label-card');
    expect(card.querySelectorAll('.label-qr-section')).toHaveLength(1);
    expect(card.querySelectorAll('.label-qr-section svg')).toHaveLength(1);
  });

  it('renders exactly one QR in print-only label card', () => {
    renderDialog();
    fillRequiredFields();
    const printCard = getPrintRoot()?.querySelector('.label-card');
    expect(printCard?.querySelectorAll('.label-qr-section')).toHaveLength(1);
    expect(printCard?.querySelectorAll('.label-qr-section svg')).toHaveLength(1);
  });

  it('renders one QR per print label when copies is 3', () => {
    renderDialog();
    fillRequiredFields();
    fireEvent.change(screen.getByRole('spinbutton', { name: /^copias$/i }), {
      target: { value: '3' },
    });
    const printRoot = getPrintRoot();
    expect(printRoot?.querySelectorAll('.label-card')).toHaveLength(3);
    expect(printRoot?.querySelectorAll('.label-qr-section')).toHaveLength(3);
    expect(printRoot?.querySelectorAll('.label-qr-section svg')).toHaveLength(3);
    expect(printRoot?.querySelectorAll('.label-qr-section').length).toBe(
      printRoot?.querySelectorAll('.label-card').length
    );
  });

  it('keeps preview and print-only roots separate', () => {
    renderDialog();
    fillRequiredFields();
    expect(document.querySelector('.label-preview-root')).toBeTruthy();
    expect(getPrintRoot()).toBeTruthy();
    expect(document.querySelector('.label-preview-root .label-print-root')).toBeFalsy();
    expect(document.querySelectorAll('.label-print-root')).toHaveLength(1);
  });

  it('uses stacked multi-label horizontal grid for multiple copies in preview', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'X1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '1' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: /^copias$/i }), {
      target: { value: '3' },
    });
    const preview = getPreviewSheet();
    const grid = within(preview).getByTestId('label-print-grid');
    expect(grid).toHaveClass('label-print-grid--horizontal');
    expect(grid).toHaveClass('multi-label');
    expect(grid).not.toHaveClass('single-label');
    expect(grid).toHaveAttribute('data-layout', 'multi');
    expect(within(preview).getAllByTestId('label-card')).toHaveLength(3);
  });

  it('wraps preview in viewport without a print root inside preview', () => {
    renderDialog();
    fillRequiredFields();
    const preview = getPreviewSheet();
    expect(preview).toHaveClass('label-preview-root');
    expect(preview.querySelector('.label-preview-viewport')).toBeTruthy();
    expect(preview.querySelector('.label-print-sheet')).toBeTruthy();
    expect(preview.querySelector('.label-card.label-card--horizontal')).toBeTruthy();
    expect(preview.querySelector('.label-print-root')).toBeFalsy();
  });

  it('renders optional footer fields inside label-footer', () => {
    renderDialog();
    fillRequiredFields();
    fireEvent.change(screen.getByRole('textbox', { name: /^lote$/i }), {
      target: { value: 'h89' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /vencimiento/i }), {
      target: { value: 'h89' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /descripción/i }), {
      target: { value: 'h89h' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /observaciones/i }), {
      target: { value: 'h89' },
    });
    const lotLine = within(getPreviewSheet()).getByText(/LOTE:/i);
    expect(lotLine.closest('.label-footer')).toBeTruthy();
    expect(within(getPreviewSheet()).getByText(/OBS:/i).closest('.label-footer')).toBeTruthy();
    const footer = getPreviewSheet().querySelector('.label-footer');
    expect(footer?.childElementCount).toBe(4);
  });

  it('unmounts print portal when dialog closes', () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <LabelGeneratorDialog
        open
        onClose={onClose}
        clientId="client-1"
        clientName="Cliente Blainstein"
        suppliers={suppliers}
      />
    );
    expect(getPrintRoot()).toBeTruthy();
    rerender(
      <LabelGeneratorDialog
        open={false}
        onClose={onClose}
        clientId="client-1"
        clientName="Cliente Blainstein"
        suppliers={suppliers}
      />
    );
    expect(getPrintRoot()).toBeFalsy();
  });

  it('renders print browser hint', () => {
    renderDialog();
    expect(screen.getByText(/encabezados y pies de página/i)).toBeInTheDocument();
  });

  it('calls window.print when Imprimir is clicked', () => {
    renderDialog();
    fillRequiredFields();
    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));
    expect(window.print).toHaveBeenCalledTimes(1);
  });

  it('sets document title before print for suggested PDF filename', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-15T12:00:00'));
    const originalTitle = 'Dinamic Inventory Test';
    document.title = originalTitle;

    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {
      expect(document.title).toBe('cliente-blainstein-1931038-03-2026-05-15');
    });

    renderDialog();
    fillRequiredFields();
    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));

    expect(printSpy).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1000);
    expect(document.title).toBe(originalTitle);

    printSpy.mockRestore();
    vi.useRealTimers();
  });

  it('restores document title after afterprint', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-15T12:00:00'));
    const originalTitle = 'Dinamic Inventory Test';
    document.title = originalTitle;

    vi.spyOn(window, 'print').mockImplementation(() => {});

    renderDialog();
    fillRequiredFields();
    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));
    expect(document.title).toBe('cliente-blainstein-1931038-03-2026-05-15');

    window.dispatchEvent(new Event('afterprint'));
    expect(document.title).toBe(originalTitle);

    vi.useRealTimers();
  });

  it('does not change document title when validation fails', () => {
    const originalTitle = 'Dinamic Inventory Test';
    document.title = originalTitle;
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});

    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));

    expect(printSpy).not.toHaveBeenCalled();
    expect(document.title).toBe(originalTitle);

    printSpy.mockRestore();
  });

  it('disables print until code and quantity are provided', () => {
    renderDialog();
    expect(screen.getByRole('button', { name: /^imprimir$/i })).toBeDisabled();
  });

  it('clears manual fields but keeps client and supplier', () => {
    renderDialog();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /proveedor/i }));
    fireEvent.click(screen.getByRole('option', { name: /proveedor rabbione/i }));
    fireEvent.change(screen.getByRole('textbox', { name: /contado por/i }), {
      target: { value: 'Ana' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'TMP' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '99' },
    });
    fireEvent.click(screen.getByRole('button', { name: /limpiar campos/i }));
    expect(screen.getByDisplayValue('Cliente Blainstein')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /proveedor/i })).toHaveTextContent(/proveedor rabbione/i);
    expect(screen.getByRole('textbox', { name: /contado por/i })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: /código interno/i })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: /cant\. total/i })).toHaveValue('');
  });
});
