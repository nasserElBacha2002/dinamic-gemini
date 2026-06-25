import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultsTable from '../src/features/results/components/ResultsTable';
import { buildResultsTableColumns } from '../src/features/results/components/resultsTableColumns';
import { getReviewStatusLabel } from '../src/features/results/utils/reviewStatusDisplay';
import type { ResultSummary } from '../src/features/results/types';
import i18n from '../src/i18n';

function imageMismatchRow(): ResultSummary {
  return {
    id: 'pos-mismatch',
    sku: 'SKU-M',
    positionCode: 'P1',
    detectedQty: 2,
    correctedQty: null,
    resolvedQty: 2,
    confidence: 0.9,
    reviewStatus: 'IMAGE_MISMATCH',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-02T00:00:00Z',
    hasEvidence: true,
    hasValidEvidence: false,
  };
}

function confirmedRow(): ResultSummary {
  return {
    id: 'pos-ok',
    sku: 'SKU-OK',
    positionCode: 'P2',
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: 1,
    confidence: 0.95,
    reviewStatus: 'CONFIRMED',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-02T00:00:00Z',
    hasEvidence: true,
    hasValidEvidence: true,
  };
}

function qtyColumnCell(row: ResultSummary) {
  const t = i18n.t.bind(i18n);
  const col = buildResultsTableColumns({ t, dash: '—', onOpenReview: vi.fn() }).find(
    (c) => c.id === 'qty'
  );
  return col!.cell(row);
}

describe('ResultsTable quantity and invalid display', () => {
  it('shows corrected resolved quantity in qty column', () => {
    const row: ResultSummary = {
      ...confirmedRow(),
      detectedQty: 10,
      correctedQty: 20,
      resolvedQty: 20,
    };
    const { container } = render(
      <ThemeProvider theme={theme}>{qtyColumnCell(row)}</ThemeProvider>
    );
    expect(container.textContent).toBe('20');
  });

  it('invalid row shows Inválido in review column', () => {
    const t = i18n.t.bind(i18n);
    const reviewCol = buildResultsTableColumns({
      t,
      dash: '—',
      onOpenReview: vi.fn(),
    }).find((c) => c.id === 'review_status');
    const row: ResultSummary = {
      ...confirmedRow(),
      id: 'pos-invalid',
      reviewStatus: 'INVALID',
    };
    const { container } = render(
      <ThemeProvider theme={theme}>{reviewCol!.cell(row)}</ThemeProvider>
    );
    expect(container.textContent).toMatch(
      new RegExp(getReviewStatusLabel('INVALID'), 'i')
    );
  });
});

describe('ResultsTable image mismatch display', () => {
  it('review column shows Confirmado; traceability column shows image mismatch warning', () => {
    const t = i18n.t.bind(i18n);
    const columns = buildResultsTableColumns({
      t,
      dash: '—',
      onOpenReview: vi.fn(),
    });
    const reviewCol = columns.find((c) => c.id === 'review_status');
    const traceCol = columns.find((c) => c.id === 'traceability');
    expect(reviewCol).toBeDefined();
    expect(traceCol).toBeDefined();

    const row = imageMismatchRow();
    const { container: reviewContainer } = render(
      <ThemeProvider theme={theme}>{reviewCol!.cell(row)}</ThemeProvider>
    );
    expect(reviewContainer.textContent).toMatch(/confirmado|confirmed/i);
    expect(reviewContainer.textContent).not.toMatch(/imagen no coincide|image mismatch/i);

    const { container: traceContainer } = render(
      <ThemeProvider theme={theme}>{traceCol!.cell(row)}</ThemeProvider>
    );
    expect(traceContainer.textContent).toMatch(/imagen no coincide|image mismatch/i);
    expect(traceContainer.textContent).not.toMatch(/\bválida\b|\bvalid\b/i);
  });

  it('image mismatch replaces valid traceability chip instead of stacking both', () => {
    const t = i18n.t.bind(i18n);
    const traceCol = buildResultsTableColumns({
      t,
      dash: '—',
      onOpenReview: vi.fn(),
    }).find((c) => c.id === 'traceability');
    const { container } = render(
      <ThemeProvider theme={theme}>{traceCol!.cell(imageMismatchRow())}</ThemeProvider>
    );
    expect(container.textContent).toMatch(/imagen no coincide|image mismatch/i);
    expect(container.textContent).not.toMatch(/\bválida\b|\bvalid\b/i);
    expect(container.textContent).not.toMatch(/ID presente en imágenes analizadas/i);
  });

  it('confirmed row with valid traceability shows sent-frame id chip only', () => {
    const t = i18n.t.bind(i18n);
    const traceCol = buildResultsTableColumns({
      t,
      dash: '—',
      onOpenReview: vi.fn(),
    }).find((c) => c.id === 'traceability');
    const { container } = render(
      <ThemeProvider theme={theme}>{traceCol!.cell(confirmedRow())}</ThemeProvider>
    );
    expect(container.textContent).toMatch(/ID presente en imágenes analizadas/i);
    expect(container.textContent).not.toMatch(/\bválida\b|\bvalid\b/i);
    expect(container.textContent).not.toMatch(/imagen no coincide|evidencia incorrecta|image mismatch/i);
  });

  it('confirmed row does not show image mismatch evidence warning in traceability column', () => {
    const t = i18n.t.bind(i18n);
    const traceCol = buildResultsTableColumns({
      t,
      dash: '—',
      onOpenReview: vi.fn(),
    }).find((c) => c.id === 'traceability');
    const { container } = render(
      <ThemeProvider theme={theme}>{traceCol!.cell(confirmedRow())}</ThemeProvider>
    );
    expect(container.textContent).not.toMatch(/imagen no coincide|evidencia incorrecta|image mismatch/i);
  });

  it('renders table with image mismatch row in review and traceability columns', () => {
    render(
      <ThemeProvider theme={theme}>
        <ResultsTable results={[imageMismatchRow(), confirmedRow()]} onOpenReview={vi.fn()} />
      </ThemeProvider>
    );
    expect(screen.getAllByText(/confirmado|confirmed/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/imagen no coincide|image mismatch/i)).toBeInTheDocument();
    expect(screen.getByText(/ID presente en imágenes analizadas/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Válida$/i)).not.toBeInTheDocument();
  });
});
