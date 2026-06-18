import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultSummaryCard from '../src/features/results/components/detail/ResultSummaryCard';
import type { ResultDetail } from '../src/features/results/types';

function imageMismatchDetail(): ResultDetail {
  return {
    id: 'pos-mismatch',
    sku: 'SKU-M',
    positionCode: 'P1',
    detectedQty: 2,
    correctedQty: null,
    resolvedQty: 2,
    systemQty: 2,
    confidence: 0.9,
    reviewStatus: 'IMAGE_MISMATCH',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-02T00:00:00Z',
    sourceImageId: null,
    sourceFileName: null,
    evidence: [],
    reviewHistory: [],
    hasValidEvidence: false,
  };
}

describe('ResultSummaryCard traceability display', () => {
  it('image mismatch shows evidence chip only, not valid traceability', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <ResultSummaryCard result={imageMismatchDetail()} />
      </ThemeProvider>
    );
    expect(container.textContent).toMatch(/evidencia incorrecta|imagen no coincide|evidence issue|image mismatch/i);
    expect(container.textContent).not.toMatch(/\bválida\b|\bvalid\b|ID presente en imágenes analizadas/i);
    expect(container.textContent).toMatch(/confirmado|confirmed/i);
  });
});
