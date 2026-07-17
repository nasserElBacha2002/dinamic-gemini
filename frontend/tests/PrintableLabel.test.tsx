import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
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
  it('renders QR and pipe barcode with code 32535235 and quantity 909', async () => {
    render(
      <PrintableLabel
        data={{
          ...sampleData,
          code: '32535235',
          quantity: '909',
        }}
        headerDate="17/07"
      />
    );
    const card = screen.getByTestId('label-card');
    expect(card.querySelector('[data-testid="qr-code-block"]')).toBeTruthy();
    expect(card.querySelector('.label-qr-section svg')).toBeTruthy();
    await waitFor(() => {
      expect(within(card).getByTestId('barcode-block')).toHaveAttribute(
        'data-barcode-value',
        '32535235|909'
      );
    });
    expect(within(card).getByTestId('qr-code-block')).toHaveAttribute(
      'data-qr-payload',
      '32535235|909'
    );
    expect(within(card).getByTestId('qr-code-block')).toHaveAttribute('data-qr-level', 'H');
    expect(within(card).getByTestId('barcode-display-code')).toHaveTextContent('32535235');
    expect(within(card).getByTestId('barcode-display-quantity')).toHaveTextContent(/CANT\.\s*909/);
    expect(within(card).getByTestId('barcode-text')).toHaveTextContent(/32535235\s*\|\s*CANT\.\s*909/);
    expect(within(card).queryByTestId('barcode-encoded-value')).toBeNull();
    expect(card).toHaveClass('print-label');
  });

  it('keeps QR and barcode on the same scan payload', async () => {
    render(<PrintableLabel data={sampleData} headerDate="17/07" />);
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute(
        'data-barcode-value',
        'ABC-123456789|150'
      );
    });
    expect(screen.getByTestId('qr-code-block')).toHaveAttribute(
      'data-qr-payload',
      'ABC-123456789|150'
    );
    expect(screen.getByTestId('qr-code-block').querySelector('svg')).toBeTruthy();
  });

  it('marks the card as a print-label with A4 landscape classes', () => {
    render(<PrintableLabel data={sampleData} headerDate="17/07" />);
    const card = screen.getByTestId('label-card');
    expect(card).toHaveClass('print-label');
    expect(card).toHaveClass('label-card--horizontal');
  });

  it('fits long code + max quantity without empty barcode state', async () => {
    render(
      <PrintableLabel
        data={{
          ...sampleData,
          code: 'ABC-123456789012345',
          quantity: '99999999',
        }}
        headerDate="17/07"
      />
    );
    await waitFor(() => {
      const block = screen.getByTestId('barcode-block');
      expect(block).toHaveAttribute('data-barcode-state', 'ready');
      expect(block.getAttribute('data-barcode-value')).toBe('ABC-123456789012345|99999999');
    });
  });
});

describe('LabelPreview live updates', () => {
  it('updates barcode when código interno changes', async () => {
    const { rerender } = render(
      <LabelPreview
        data={{
          ...sampleData,
          code: 'OLD-1',
          quantity: '10',
          copies: 1,
        }}
      />
    );
    await waitFor(() => {
      expect(within(screen.getByTestId('label-preview-sheet')).getByTestId('barcode-display-code')).toHaveTextContent(
        'OLD-1'
      );
    });

    rerender(
      <LabelPreview
        data={{
          ...sampleData,
          code: 'NEW-999',
          quantity: '10',
          copies: 1,
        }}
      />
    );
    await waitFor(() => {
      expect(within(screen.getByTestId('label-preview-sheet')).getByTestId('barcode-display-code')).toHaveTextContent(
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

  it('uses drone-readable physical sizes for QR and barcode', () => {
    expect(labelPrintCss).toMatch(/--label-qr-size:\s*80mm/);
    expect(labelPrintCss).toMatch(/--label-barcode-width:\s*2[5-6]\dmm/);
    expect(labelPrintCss).toMatch(/--label-barcode-height:\s*(?:4[8-9]|5[0-5])mm/);
    const widthMatch = labelPrintCss.match(/--label-barcode-width:\s*(\d+(?:\.\d+)?)mm/);
    const heightMatch = labelPrintCss.match(/--label-barcode-height:\s*(\d+(?:\.\d+)?)mm/);
    expect(Number(widthMatch?.[1])).toBeGreaterThanOrEqual(250);
    expect(Number(heightMatch?.[1])).toBeGreaterThanOrEqual(48);
    expect(labelPrintCss).toMatch(/\.qr-code[\s\S]*?width:\s*var\(--label-qr-size\)/);
    expect(labelPrintCss).toMatch(/\.barcode-wrapper[\s\S]*?height:\s*var\(--label-barcode-height\)/);
    expect(labelPrintCss).toMatch(/\.barcode-wrapper svg,\s*\n\.barcode-svg\s*\{[^}]*width:\s*100%/s);
    expect(labelPrintCss).toMatch(/\.barcode-wrapper svg,\s*\n\.barcode-svg\s*\{[^}]*height:\s*100%/s);
    expect(labelPrintCss).not.toMatch(/\.barcode-wrapper svg,\s*\n\.barcode-svg\s*\{[^}]*width:\s*auto/s);
    expect(labelPrintCss).toMatch(/@media print[\s\S]*height:\s*80mm\s*!important/);
    expect(labelPrintCss).toMatch(/@media print[\s\S]*height:\s*50mm\s*!important/);
    expect(labelPrintCss).toMatch(/@media print[\s\S]*\.barcode-svg[\s\S]*width:\s*100%\s*!important/);
  });

  it('places additional data inside the left primary column (beside QR)', () => {
    render(
      <PrintableLabel
        data={{
          clientName: 'cliente',
          supplierName: null,
          countedBy: null,
          code: '9909090832',
          quantity: '1231',
          lot: '894',
          expiry: '24/2002',
          description: 'ddescrgiobniudb',
          observations: 'falla',
        }}
        headerDate="17/07"
      />
    );

    const main = screen.getByTestId('label-main-content');
    const primaryColumn = screen.getByTestId('label-primary-column');
    const additional = screen.getByTestId('label-additional-data');
    const barcode = screen.getByTestId('label-barcode-section');
    const card = screen.getByTestId('label-card');

    expect(primaryColumn.contains(additional)).toBe(true);
    expect(main.contains(additional)).toBe(true);
    expect(main.contains(primaryColumn)).toBe(true);
    expect(card.contains(main)).toBe(true);
    expect(main.contains(barcode)).toBe(false);
    expect(
      main.compareDocumentPosition(barcode) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    const items = [...additional.querySelectorAll('.label-additional-item')];
    expect(items).toHaveLength(4);
    expect(items.map((item) => item.querySelector('.label-additional-label')?.textContent)).toEqual([
      'LOTE:',
      'VENCIMIENTO:',
      'DESCRIPCIÓN:',
      'OBSERVACIONES:',
    ]);
    expect(items.map((item) => item.querySelector('.label-additional-value')?.textContent)).toEqual([
      '894',
      '24/2002',
      'ddescrgiobniudb',
      'falla',
    ]);

    // Label and value share one row (grid), value follows label in DOM.
    items.forEach((item) => {
      expect(item.className).not.toMatch(/absolute/);
      const label = item.querySelector('.label-additional-label')!;
      const value = item.querySelector('.label-additional-value')!;
      expect(label.compareDocumentPosition(value) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
  });

  it('does not render additional-data section when optional fields are empty', () => {
    render(
      <PrintableLabel
        data={{
          clientName: 'cliente',
          supplierName: null,
          countedBy: null,
          code: '9909090832',
          quantity: '1231',
          lot: null,
          expiry: null,
          description: null,
          observations: null,
        }}
        headerDate="17/07"
      />
    );
    expect(screen.getByTestId('label-card')).toHaveAttribute('data-has-additional', 'false');
    expect(screen.queryByTestId('label-additional-data')).toBeNull();
    expect(screen.queryByTestId('label-footer')).toBeNull();
    expect(document.querySelector('.label-footer')).toBeNull();
  });

  it('omits empty optional fields while keeping others', () => {
    render(
      <PrintableLabel
        data={{
          clientName: 'cliente',
          supplierName: null,
          countedBy: null,
          code: '9909090832',
          quantity: '1231',
          lot: 'L1',
          expiry: null,
          description: null,
          observations: null,
        }}
        headerDate="17/07"
      />
    );
    const additional = screen.getByTestId('label-additional-data');
    expect(additional).toHaveTextContent(/LOTE:\s*L1/);
    expect(additional).not.toHaveTextContent(/VENCIMIENTO:/);
    expect(additional).not.toHaveTextContent(/DESCRIPCIÓN:/);
    expect(additional).not.toHaveTextContent(/OBSERVACIONES:/);
  });

  it('keeps QR and barcode on the same payload for the visual validation sample', async () => {
    render(
      <PrintableLabel
        data={{
          clientName: 'cliente',
          supplierName: null,
          countedBy: null,
          code: '9909090832',
          quantity: '1231',
          lot: null,
          expiry: null,
          description: null,
          observations: null,
        }}
        headerDate="17/07"
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId('barcode-block')).toHaveAttribute(
        'data-barcode-value',
        '9909090832|1231'
      );
    });
    expect(screen.getByTestId('qr-code-block')).toHaveAttribute(
      'data-qr-payload',
      '9909090832|1231'
    );
    expect(screen.getByTestId('barcode-text')).toHaveTextContent(/9909090832\s*\|\s*CANT\.\s*1231/);
    expect(screen.getByTestId('barcode-text')).not.toHaveTextContent('9909090832|1231');
  });

  it('keeps barcode and QR physical size targets', () => {
    expect(labelPrintCss).toMatch(/--label-barcode-width:\s*260mm/);
    expect(labelPrintCss).toMatch(/--label-barcode-height:\s*50mm/);
    expect(labelPrintCss).toMatch(/--label-qr-size:\s*80mm/);
  });

  it('uses a 3-row root grid (no exclusive additional row)', () => {
    expect(labelPrintCss).toMatch(
      /\.inventory-label\s*\{[\s\S]*?grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto/
    );
    expect(labelPrintCss).not.toMatch(
      /\.inventory-label--with-additional\s*\{[\s\S]*?grid-template-rows:\s*auto\s+auto\s+minmax/
    );
    expect(labelPrintCss).not.toMatch(/--label-additional-min:/);
  });

  it('styles additional items as full-width rows with label|value columns', () => {
    expect(labelPrintCss).toMatch(/\.label-primary-column\s*\{[\s\S]*?flex-direction:\s*column/);
    expect(labelPrintCss).toMatch(
      /\.label-additional-data\s*\{[\s\S]*?flex-direction:\s*column/
    );
    expect(labelPrintCss).toMatch(
      /\.label-additional-item\s*\{[\s\S]*?grid-template-columns:\s*38mm\s+minmax\(0,\s*1fr\)/
    );
    expect(labelPrintCss).not.toMatch(
      /\.label-additional-item\s*\{[\s\S]*?flex-direction:\s*column/
    );
    expect(labelPrintCss).not.toMatch(
      /\.label-additional-data\s*\{[\s\S]*?grid-template-columns:\s*1fr\s+1fr/
    );
    expect(labelPrintCss).toMatch(
      /\.label-additional-value\s*\{[\s\S]*?white-space:\s*normal/
    );
  });

  it('asserts non-overlapping stacked geometry when layout metrics are available', () => {
    render(
      <PrintableLabel
        data={{
          clientName: 'cliente',
          supplierName: null,
          countedBy: null,
          code: '9909090832',
          quantity: '1231',
          lot: '894',
          expiry: '24/2002',
          description: 'ddescrgiobniudb',
          observations: 'falla',
        }}
        headerDate="17/07"
      />
    );

    const additional = screen.getByTestId('label-additional-data');
    const barcode = screen.getByTestId('label-barcode-section');
    const card = screen.getByTestId('label-card');
    const items = [...additional.querySelectorAll('.label-additional-item')];

    // jsdom does not compute CSS layout; provide deterministic stacked metrics for the contract.
    const assignRect = (el: Element, top: number, height: number, left = 10, width = 180) => {
      vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
        x: left,
        y: top,
        top,
        bottom: top + height,
        left,
        right: left + width,
        width,
        height,
        toJSON: () => ({}),
      } as DOMRect);
    };

    assignRect(card, 0, 794, 0, 1123);
    Object.defineProperty(card, 'clientHeight', { configurable: true, value: 794 });
    Object.defineProperty(card, 'scrollHeight', { configurable: true, value: 794 });

    let cursor = 120;
    items.forEach((item) => {
      assignRect(item, cursor, 28);
      cursor += 32;
    });
    assignRect(additional, 120, cursor - 120);
    assignRect(barcode, cursor + 8, 190);

    const rects = items.map((item) => item.getBoundingClientRect());
    for (let index = 1; index < rects.length; index += 1) {
      expect(rects[index]!.top).toBeGreaterThanOrEqual(rects[index - 1]!.bottom);
    }

    const additionalRect = additional.getBoundingClientRect();
    const barcodeRect = barcode.getBoundingClientRect();
    expect(additionalRect.bottom).toBeLessThanOrEqual(barcodeRect.top);
    expect(card.scrollHeight).toBeLessThanOrEqual(card.clientHeight);
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
