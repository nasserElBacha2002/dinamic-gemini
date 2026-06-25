import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../../../src/theme';
import CodeScanSummaryTable from '../../../src/features/aisle-code-scans/components/CodeScanSummaryTable';
import type { CodeScanSummaryItem } from '../../../src/api/types/codeScans';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../../src/features/aisle-code-scans/components/CopyCodeValueButton', () => ({
  default: () => <button type="button">copy</button>,
}));

function makeItem(index: number): CodeScanSummaryItem {
  return {
    code_value: `CODE-${index}`,
    normalized_code_value: `CODE-${index}`,
    code_type: 'barcode',
    occurrences: 1,
    asset_ids: [`asset-${index}`],
    first_seen_at: '2026-05-20T12:00:00Z',
    match_status: 'matched',
    matched_position_ids: [`pos-${index}`],
    match_types: ['barcode_exact'],
  };
}

describe('CodeScanSummaryTable pagination', () => {
  it('paginates summary rows when list exceeds page size', () => {
    const items = Array.from({ length: 30 }, (_, i) => makeItem(i + 1));
    render(
      <ThemeProvider theme={theme}>
        <CodeScanSummaryTable items={items} />
      </ThemeProvider>
    );

    expect(screen.getByText('CODE-1')).toBeInTheDocument();
    expect(screen.getByText('CODE-25')).toBeInTheDocument();
    expect(screen.queryByText('CODE-26')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('CODE-26')).toBeInTheDocument();
  });

  it('resets to page 1 when items dataset shrinks after navigating to page 2', () => {
    const fullItems = Array.from({ length: 30 }, (_, i) => makeItem(i + 1));
    const shortItems = Array.from({ length: 5 }, (_, i) => makeItem(i + 1));
    const { rerender } = render(
      <ThemeProvider theme={theme}>
        <CodeScanSummaryTable items={fullItems} />
      </ThemeProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('CODE-26')).toBeInTheDocument();
    expect(screen.queryByText('CODE-1')).not.toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <CodeScanSummaryTable items={shortItems} />
      </ThemeProvider>
    );

    expect(screen.getByText('CODE-1')).toBeInTheDocument();
    expect(screen.getByText('CODE-5')).toBeInTheDocument();
    expect(screen.queryByText('CODE-26')).not.toBeInTheDocument();
  });
});
