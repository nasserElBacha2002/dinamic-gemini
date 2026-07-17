import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import BarcodeBlock from '../src/features/clients/components/BarcodeBlock';

describe('BarcodeBlock', () => {
  it('does not generate a barcode when value is empty', () => {
    render(<BarcodeBlock value="" displayCode="" displayQuantity="" />);
    const block = screen.getByTestId('barcode-block');
    expect(block).toHaveAttribute('data-barcode-state', 'empty');
    expect(block.querySelector('svg.barcode-svg')).toBeNull();
    expect(screen.getByText(/completá el código interno/i)).toBeInTheDocument();
  });

  it('renders CODE128 with DI1 payload and human-readable code + quantity', async () => {
    const onValidityChange = vi.fn();
    render(
      <BarcodeBlock
        value="DI1|C=32535235|Q=909"
        displayCode="32535235"
        displayQuantity="909"
        onValidityChange={onValidityChange}
      />
    );
    const block = screen.getByTestId('barcode-block');
    await waitFor(() => {
      expect(block).toHaveAttribute('data-barcode-state', 'ready');
    });
    expect(block).toHaveAttribute('data-barcode-format', 'CODE128');
    expect(block).toHaveAttribute('data-barcode-value', 'DI1|C=32535235|Q=909');
    expect(block).toHaveAttribute('data-barcode-payload', 'DI1|C=32535235|Q=909');
    expect(screen.getByTestId('barcode-display-code')).toHaveTextContent('32535235');
    expect(screen.getByTestId('barcode-display-quantity')).toHaveTextContent(/CANT\.\s*909/);
    expect(onValidityChange).toHaveBeenCalledWith(true);
  });

  it('does not show the technical payload as primary human text', async () => {
    render(
      <BarcodeBlock value="DI1|C=ABC-123|Q=150" displayCode="ABC-123" displayQuantity="150" />
    );
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-state', 'ready');
    });
    expect(screen.getByTestId('barcode-text')).not.toHaveTextContent('DI1|');
    expect(screen.getByText('ABC-123')).toBeInTheDocument();
    expect(screen.getByText(/CANT\.\s*150/)).toBeInTheDocument();
  });
});
