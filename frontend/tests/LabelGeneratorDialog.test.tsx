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
  render(
    <LabelGeneratorDialog
      open
      onClose={onClose}
      clientId="client-1"
      clientName="Cliente Blainstein"
      suppliers={suppliers}
      {...overrides}
    />
  );
  return { onClose };
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

  it('renders horizontal label card and warehouse title', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '205357' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '7200' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    const card = within(sheet).getByTestId('label-card');
    expect(card).toHaveClass('label-card--horizontal');
    expect(within(sheet).getByText(LABEL_PRINT_TITLE)).toBeInTheDocument();
  });

  it('renders CÓDIGO INTERNO and CANT. TOTAL labels instead of COD/CANTIDAD', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'ABC' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '10' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).getByText('CÓDIGO INTERNO:')).toBeInTheDocument();
    expect(within(sheet).getByText('CANT. TOTAL')).toBeInTheDocument();
    expect(within(sheet).queryByText(/^COD:/)).not.toBeInTheDocument();
    expect(within(sheet).queryByText(/^CANTIDAD:/)).not.toBeInTheDocument();
  });

  it('shows code and quantity values prominently in preview', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '10334321' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '34' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).getByText('10334321')).toHaveClass('label-code-value');
    expect(within(sheet).getByText('34')).toHaveClass('label-quantity-value');
  });

  it('updates preview when Contado por is filled', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'X' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /contado por/i }), {
      target: { value: 'Ana López' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).getByText('CONTADO POR:')).toBeInTheDocument();
    expect(within(sheet).getByText('Ana López')).toBeInTheDocument();
  });

  it('omits empty optional fields from the label', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'ABC' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '10' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).queryByText('LOTE:')).not.toBeInTheDocument();
    expect(within(sheet).queryByText('CONTADO POR:')).not.toBeInTheDocument();
    expect(within(sheet).queryByText('PROVEEDOR:')).not.toBeInTheDocument();
  });

  it('uses single-label horizontal grid for one copy', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: 'X1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '1' },
    });
    const grid = screen.getByTestId('label-print-grid');
    expect(grid).toHaveClass('label-print-grid--horizontal');
    expect(grid).toHaveClass('single-label');
    expect(grid).toHaveAttribute('data-layout', 'single');
    expect(screen.getAllByTestId('label-card')).toHaveLength(1);
  });

  it('renders exactly one printable root and one label card for a single copy', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '1931038' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '03' },
    });
    expect(document.querySelectorAll('.label-print-root')).toHaveLength(1);
    expect(document.querySelectorAll('.label-print-root .label-card')).toHaveLength(1);
    expect(screen.getByTestId('label-print-grid')).toHaveAttribute('data-copies', '1');
    expect(screen.getByTestId('label-print-grid')).toHaveClass('single-label');
  });

  it('renders three printable label cards when copies is 3', () => {
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
    expect(document.querySelectorAll('.label-print-root')).toHaveLength(1);
    expect(document.querySelectorAll('.label-print-root .label-card')).toHaveLength(3);
    expect(screen.getByTestId('label-print-grid')).toHaveAttribute('data-copies', '3');
  });

  it('uses stacked multi-label horizontal grid for multiple copies', () => {
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
    const grid = screen.getByTestId('label-print-grid');
    expect(grid).toHaveClass('label-print-grid--horizontal');
    expect(grid).toHaveClass('multi-label');
    expect(grid).not.toHaveClass('single-label');
    expect(grid).toHaveAttribute('data-layout', 'multi');
    expect(screen.getAllByTestId('label-card')).toHaveLength(3);
  });

  it('wraps preview in viewport and uses same LabelPrintSheet DOM as print', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '05' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '544' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(sheet).toHaveClass('label-preview-root');
    expect(sheet.querySelector('.label-print-root')).toBeTruthy();
    expect(sheet.querySelector('.label-preview-viewport')).toBeTruthy();
    expect(sheet.querySelector('.label-print-sheet')).toBeTruthy();
    expect(sheet.querySelector('.label-card.label-card--horizontal')).toBeTruthy();
  });

  it('renders optional footer fields inside label-footer', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '05' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '544' },
    });
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
    const lotLine = screen.getByText(/LOTE:/i);
    expect(lotLine.closest('.label-footer')).toBeTruthy();
    expect(screen.getByText(/OBS:/i).closest('.label-footer')).toBeTruthy();
    const footer = screen.getByTestId('label-print-sheet').querySelector('.label-footer');
    expect(footer?.childElementCount).toBe(4);
  });

  it('renders print browser hint', () => {
    renderDialog();
    expect(screen.getByText(/encabezados y pies de página/i)).toBeInTheDocument();
  });

  it('calls window.print when Imprimir is clicked', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /código interno/i }), {
      target: { value: '205357' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /cant\. total/i }), {
      target: { value: '7200' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^imprimir$/i }));
    expect(window.print).toHaveBeenCalledTimes(1);
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
