import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { PrintableLabel, LabelPreview } from '../src/features/clients/components/LabelPrintSheet';
import type { LabelSheetData } from '../src/features/clients/components/labelPrintUtils';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const labelPrintCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../src/features/clients/components/labelPrint.css'),
  'utf8'
);

const sampleData: Omit<LabelSheetData, 'copies'> = {
  clientName: 'blestein',
  supplierName: 'ejemplo',
  countedBy: 'operador',
  code: 'ABC-123456789',
  quantity: '150',
  lot: 'LOTE-2026-01',
  expiry: '31/12/2026',
  description: 'Mercadería en pallets',
  observations: 'Controlar lote y vencimiento',
};

describe('PrintableLabel barcode + QR', () => {
  it('renders QR and barcode together without removing QR', async () => {
    render(<PrintableLabel data={sampleData} headerDate="17/07" />);
    const card = screen.getByTestId('label-card');
    expect(card.querySelector('[data-testid="qr-code-block"]')).toBeTruthy();
    expect(card.querySelector('.label-qr-section svg')).toBeTruthy();
    await waitFor(() => {
      expect(within(card).getByTestId('barcode-block')).toHaveAttribute('data-barcode-state', 'ready');
    });
    expect(within(card).getByTestId('barcode-text')).toHaveTextContent('ABC-123456789');
  });

  it('uses código interno for the barcode value', async () => {
    render(<PrintableLabel data={sampleData} headerDate="17/07" />);
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute('data-barcode-value', 'ABC-123456789');
    });
  });

  it('marks the card as a print-label with A4 landscape classes', () => {
    render(<PrintableLabel data={sampleData} headerDate="17/07" />);
    const card = screen.getByTestId('label-card');
    expect(card).toHaveClass('print-label');
    expect(card).toHaveClass('label-card--horizontal');
  });
});

describe('LabelPreview live updates', () => {
  it('updates barcode when código interno changes', async () => {
    const { rerender } = render(
      <LabelPreview
        data={{
          ...sampleData,
          code: 'OLD-1',
          copies: 1,
        }}
      />
    );
    await waitFor(() => {
      expect(within(screen.getByTestId('label-preview-sheet')).getByTestId('barcode-text')).toHaveTextContent(
        'OLD-1'
      );
    });

    rerender(
      <LabelPreview
        data={{
          ...sampleData,
          code: 'NEW-999',
          copies: 1,
        }}
      />
    );
    await waitFor(() => {
      expect(within(screen.getByTestId('label-preview-sheet')).getByTestId('barcode-text')).toHaveTextContent(
        'NEW-999'
      );
    });
  });

  it('does not generate barcode in preview when code is empty', () => {
    render(
      <LabelPreview
        data={{
          ...sampleData,
          code: '',
          copies: 1,
        }}
      />
    );
    expect(within(screen.getByTestId('label-preview-sheet')).getByTestId('barcode-block')).toHaveAttribute(
      'data-barcode-state',
      'empty'
    );
  });

  it('renders one page per copy and last page without forced break class pair', () => {
    render(
      <LabelPreview
        data={{
          ...sampleData,
          copies: 2,
        }}
      />
    );
    const cards = within(screen.getByTestId('label-preview-sheet')).getAllByTestId('label-card');
    expect(cards).toHaveLength(2);
    expect(cards.every((card) => card.classList.contains('print-label'))).toBe(true);
  });
});

describe('label print CSS contracts', () => {
  it('uses A4 landscape page size with zero margin', () => {
    expect(labelPrintCss).toMatch(/@page\s*\{[^}]*size:\s*A4 landscape/s);
    expect(labelPrintCss).toMatch(/@page\s*\{[^}]*margin:\s*0/s);
  });

  it('sizes print labels to full A4 landscape', () => {
    expect(labelPrintCss).toMatch(/\.print-label[\s\S]*?width:\s*297mm/);
    expect(labelPrintCss).toMatch(/\.print-label[\s\S]*?height:\s*210mm/);
  });

  it('forces page break after each label except the last', () => {
    expect(labelPrintCss).toMatch(/\.print-label:last-child[\s\S]*?page-break-after:\s*auto/);
    expect(labelPrintCss).toMatch(/page-break-after:\s*always/);
  });

  it('constrains QR and barcode containers', () => {
    expect(labelPrintCss).toMatch(/\.qr-code[\s\S]*?width:\s*24mm/);
    expect(labelPrintCss).toMatch(/\.barcode-wrapper[\s\S]*?max-width:\s*65mm/);
    expect(labelPrintCss).toMatch(/max-height:\s*22mm/);
  });

  it('hides non-print UI and .no-print in print media', () => {
    expect(labelPrintCss).toMatch(/\.no-print\s*\{[^}]*display:\s*none\s*!important/s);
    expect(labelPrintCss).toMatch(/body\s*>\s*\*:not\(\.label-print-only-root\)/);
  });

  it('keeps print overflow hidden on labels and html/body', () => {
    expect(labelPrintCss).toMatch(/@media print[\s\S]*overflow:\s*hidden/s);
    expect(labelPrintCss).toMatch(/\.print-label[\s\S]*overflow:\s*hidden/s);
  });
});
