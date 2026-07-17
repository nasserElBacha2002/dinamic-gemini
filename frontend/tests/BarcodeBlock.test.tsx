import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import BarcodeBlock from '../src/features/clients/components/BarcodeBlock';

describe('BarcodeBlock', () => {
  it('does not generate a barcode when value is empty', () => {
    render(<BarcodeBlock value="   " />);
    const block = screen.getByTestId('barcode-block');
    expect(block).toHaveAttribute('data-barcode-state', 'empty');
    expect(block.querySelector('svg.barcode-svg')).toBeNull();
    expect(screen.getByText(/completá el código interno/i)).toBeInTheDocument();
  });

  it('renders CODE128 barcode for alphanumeric internal codes', async () => {
    render(<BarcodeBlock value="ABC-123456" />);
    const block = screen.getByTestId('barcode-block');
    await waitFor(() => {
      expect(block).toHaveAttribute('data-barcode-state', 'ready');
    });
    expect(block).toHaveAttribute('data-barcode-format', 'CODE128');
    expect(block).toHaveAttribute('data-barcode-value', 'ABC-123456');
    expect(block.querySelector('svg.barcode-svg')).toBeTruthy();
    expect(screen.getByTestId('barcode-text')).toHaveTextContent('ABC-123456');
  });

  it('trims accidental spaces before encoding', async () => {
    render(<BarcodeBlock value="  ABC-123  " />);
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-value', 'ABC-123');
    });
    expect(screen.getByTestId('barcode-text')).toHaveTextContent('ABC-123');
  });

  it('shows text under barcode matching the encoded value', async () => {
    render(<BarcodeBlock value="LOTE-2026-01" />);
    await waitFor(() => {
      expect(screen.getByTestId('barcode-text')).toHaveTextContent('LOTE-2026-01');
    });
  });
});
