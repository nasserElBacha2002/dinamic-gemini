import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import LabelGeneratorDialog from '../src/features/clients/components/LabelGeneratorDialog';

const suppliers = [
  {
    id: 'supplier-1',
    client_id: 'client-1',
    name: 'Proveedor Rabbione',
    status: 'active',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
];

function renderDialog(overrides: Partial<Parameters<typeof LabelGeneratorDialog>[0]> = {}) {
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

  it('updates preview when code and quantity are entered', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: '205357' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
      target: { value: '7200' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).getByText('205357')).toBeInTheDocument();
    expect(within(sheet).getByText('7200')).toBeInTheDocument();
  });

  it('omits empty optional fields from the label', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: 'ABC' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
      target: { value: '10' },
    });
    const sheet = screen.getByTestId('label-print-sheet');
    expect(within(sheet).queryByText('LOTE:')).not.toBeInTheDocument();
    expect(within(sheet).queryByText('VTO:')).not.toBeInTheDocument();
    expect(within(sheet).queryByText('DESCRIPCION:')).not.toBeInTheDocument();
  });

  it('uses single-label grid layout for one copy', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: 'X1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
      target: { value: '1' },
    });
    const grid = screen.getByTestId('label-print-grid');
    expect(grid).toHaveClass('single-label');
    expect(grid).toHaveAttribute('data-layout', 'single');
    expect(screen.getAllByTestId('label-card')).toHaveLength(1);
  });

  it('uses multi-label grid layout for multiple copies', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: 'X1' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
      target: { value: '1' },
    });
    fireEvent.change(screen.getByRole('spinbutton', { name: /^copias$/i }), {
      target: { value: '3' },
    });
    const grid = screen.getByTestId('label-print-grid');
    expect(grid).toHaveClass('multi-label');
    expect(grid).toHaveAttribute('data-layout', 'multi');
    expect(screen.getAllByTestId('label-card')).toHaveLength(3);
  });

  it('renders print browser hint', () => {
    renderDialog();
    expect(screen.getByText(/encabezados y pies de página/i)).toBeInTheDocument();
  });

  it('calls window.print when Imprimir is clicked', () => {
    renderDialog();
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: '205357' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
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
    fireEvent.change(screen.getByRole('textbox', { name: /^código$/i }), {
      target: { value: 'TMP' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: /^cantidad$/i }), {
      target: { value: '99' },
    });
    fireEvent.click(screen.getByRole('button', { name: /limpiar campos/i }));
    expect(screen.getByDisplayValue('Cliente Blainstein')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /proveedor/i })).toHaveTextContent(/proveedor rabbione/i);
    expect(screen.getByRole('textbox', { name: /^código$/i })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: /^cantidad$/i })).toHaveValue('');
  });
});
