import React from 'react';
import type { ReactNode } from 'react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import CreateAisleDialog from '../src/components/CreateAisleDialog';

const { useClientSuppliersMock } = vi.hoisted(() => ({
  useClientSuppliersMock: vi.fn(),
}));

vi.mock('../src/hooks/useClients', () => ({
  useClientSuppliers: useClientSuppliersMock,
}));

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('CreateAisleDialog', () => {
  beforeEach(() => {
    useClientSuppliersMock.mockReset();
    useClientSuppliersMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
    });
  });

  it('validates required aisle code inline', async () => {
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={async () => ({})}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(
      await screen.findByText(/ingresá el código del pasillo|validation code required|código obligatorio/i)
    ).toBeInTheDocument();
  });

  it('pre-validates duplicate code when existing codes are provided', async () => {
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          existingAisleCodes={['A-01']}
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={async () => ({})}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: ' a-01 ' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(
      await screen.findByText(/ya existe un pasillo|validation duplicate|ya existe|duplicad/i)
    ).toBeInTheDocument();
  });

  it('shows success state with create another and close actions', async () => {
    const createAisleFn = vi.fn(async () => ({ id: 'a1' }));
    const onSuccess = vi.fn();
    const onClose = vi.fn();

    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          onClose={onClose}
          onSuccess={onSuccess}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(screen.getByRole('alert')).toHaveTextContent(/success created|creado|A1/i);
    expect(screen.getByRole('button', { name: /create another|crear otro/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cerrar|close/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /create another|crear otro/i }));
    expect(screen.queryByText(/created|creado/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/código|code label/i)).toHaveValue('');
    expect(screen.getByLabelText(/código|code label/i)).toHaveFocus();
  });

  it('renders supplier selector and scopes supplier query by inventory client', () => {
    useClientSuppliersMock.mockReturnValue({
      data: { items: [{ id: 'sup-1', name: 'Proveedor Uno' }] },
      isLoading: false,
      isError: false,
    });

    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={async () => ({})}
        />
      </WithTheme>
    );

    expect(screen.getByRole('combobox', { name: /^proveedor$/i })).toBeInTheDocument();
    expect(useClientSuppliersMock).toHaveBeenCalledWith(
      'cli-1',
      { page: 1, page_size: 200 },
      { enabled: true }
    );
  });

  it('submits selected supplier as client_supplier_id when inventory has client', async () => {
    const createAisleFn = vi.fn(async () => ({ id: 'a1' }));
    useClientSuppliersMock.mockReturnValue({
      data: {
        items: [
          { id: 'sup-1', name: 'Proveedor Uno' },
          { id: 'sup-2', name: 'Proveedor Dos' },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^proveedor$/i }));
    fireEvent.click(screen.getByRole('option', { name: /proveedor dos/i }));
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));

    await waitFor(() => {
      expect(createAisleFn).toHaveBeenCalledTimes(1);
      expect(createAisleFn).toHaveBeenCalledWith({ code: 'A1', client_supplier_id: 'sup-2' });
    });
  });

  it('blocks submit when supplier is missing and inventory has client', async () => {
    const createAisleFn = vi.fn(async () => ({}));
    useClientSuppliersMock.mockReturnValue({
      data: { items: [{ id: 'sup-1', name: 'Proveedor Uno' }] },
      isLoading: false,
      isError: false,
    });
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));

    expect(await screen.findByText(/seleccioná un proveedor para crear el pasillo/i)).toBeInTheDocument();
    expect(createAisleFn).not.toHaveBeenCalled();
  });

  it('blocks submit while suppliers are loading for inventory with client', async () => {
    const createAisleFn = vi.fn(async () => ({}));
    useClientSuppliersMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    const supplierSelect = screen.getByRole('combobox', { name: /^proveedor$/i });
    expect(supplierSelect).toHaveAttribute('aria-disabled', 'true');
    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(await screen.findByText(/cargando proveedores del cliente/i)).toBeInTheDocument();
    expect(createAisleFn).not.toHaveBeenCalled();
  });

  it('shows supplier load error and blocks submit for inventory with client', async () => {
    const createAisleFn = vi.fn(async () => ({}));
    useClientSuppliersMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(await screen.findByText(/no se pudieron cargar los proveedores del cliente/i)).toBeInTheDocument();
    expect(createAisleFn).not.toHaveBeenCalled();
  });

  it('shows empty suppliers helper and blocks submit for inventory with client', async () => {
    const createAisleFn = vi.fn(async () => ({}));
    useClientSuppliersMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
    });
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId="cli-1"
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    expect(screen.getByText(/este cliente todavía no tiene proveedores cargados/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));
    expect(createAisleFn).not.toHaveBeenCalled();
  });

  it('keeps legacy flow without client and never sends empty client_supplier_id', async () => {
    const createAisleFn = vi.fn(async () => ({ id: 'a1' }));
    render(
      <WithTheme>
        <CreateAisleDialog
          open
          inventoryId="inv_1"
          inventoryClientId={null}
          onClose={() => {}}
          onSuccess={() => {}}
          createAisleFn={createAisleFn}
        />
      </WithTheme>
    );

    expect(
      screen.getByText(/este inventario no tiene cliente asociado\. podés crear el pasillo sin proveedor por ahora/i)
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/código|code label/i), { target: { value: 'A1' } });
    fireEvent.click(screen.getByRole('button', { name: /crear pasillo|create/i }));

    await waitFor(() => {
      expect(createAisleFn).toHaveBeenCalledTimes(1);
      expect(createAisleFn).toHaveBeenCalledWith({ code: 'A1' });
    });
  });
});

