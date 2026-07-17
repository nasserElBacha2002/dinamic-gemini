import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import BarcodeBlock from '../src/features/clients/components/BarcodeBlock';

describe('BarcodeBlock', () => {
  it('shows empty state without value', () => {
    render(<BarcodeBlock value="" displayCode="" displayQuantity="" />);
    expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-state', 'empty');
  });

  it('renders CODE128 with pipe payload and non-duplicated human text', async () => {
    render(
      <BarcodeBlock value="32535235|909" displayCode="32535235" displayQuantity="909" />
    );

    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-state', 'ready');
    });
    const block = screen.getByTestId('barcode-block');
    expect(block).toHaveAttribute('data-barcode-format', 'CODE128');
    expect(block).toHaveAttribute('data-barcode-value', '32535235|909');
    expect(block).toHaveAttribute('data-barcode-payload', '32535235|909');
    expect(screen.queryByTestId('barcode-encoded-value')).toBeNull();
    expect(screen.getByTestId('barcode-display-code')).toHaveTextContent('32535235');
    expect(screen.getByTestId('barcode-display-quantity')).toHaveTextContent(/CANT\.\s*909/);
    expect(screen.getByTestId('barcode-text')).toHaveTextContent(/32535235\s*\|\s*CANT\.\s*909/);
    expect(screen.getByTestId('barcode-text')).not.toHaveTextContent('32535235|909');

    const svg = block.querySelector('svg.barcode-svg');
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute('viewBox')).toMatch(/^0 0 /);
    expect(svg?.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet');
    expect(svg?.hasAttribute('width')).toBe(false);
    expect(svg?.hasAttribute('height')).toBe(false);
  });

  it('does not surface raw DI1 version text for pipe payloads', async () => {
    render(<BarcodeBlock value="ABC-123|150" displayCode="ABC-123" displayQuantity="150" />);
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-state', 'ready');
    });
    expect(screen.getByTestId('barcode-text')).not.toHaveTextContent('DI1|');
  });
});
