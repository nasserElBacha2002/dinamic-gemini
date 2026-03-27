/**
 * Sprint 5.2 — inline validation for review corrections.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultReviewActions from '../src/features/results/components/detail/ResultReviewActions';
import type { ResultDetail } from '../src/features/results/types';

function WithTheme({ children }: { children: React.ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

const baseResult: ResultDetail = {
  id: 'pos-1',
  sku: 'SKU-1',
  detectedQty: 3,
  correctedQty: null,
  resolvedQty: 3,
  systemQty: 3,
  confidence: 0.9,
  reviewStatus: 'DETECTED',
  traceabilityStatus: 'UNVALIDATED',
  needsReview: true,
  updatedAt: '2024-01-01T00:00:00Z',
  sourceImageId: null,
  sourceFileName: null,
  evidence: [],
  reviewHistory: [],
};

describe('ResultReviewActions', () => {
  it('shows inline error when quantity is invalid', () => {
    const onUpdateQuantity = vi.fn();
    render(
      <WithTheme>
        <ResultReviewActions
          result={baseResult}
          actionLoading={false}
          onConfirm={vi.fn()}
          onUpdateQuantity={onUpdateQuantity}
          onUpdateSku={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    const qtyInput = screen.getByLabelText(/Corrected quantity/i);
    fireEvent.change(qtyInput, { target: { value: '-1' } });
    fireEvent.click(screen.getByRole('button', { name: /Update quantity/i }));
    expect(screen.getByText(/whole number 0 or greater/i)).toBeInTheDocument();
    expect(onUpdateQuantity).not.toHaveBeenCalled();
  });

  it('shows inline error when SKU is empty on update', () => {
    const onUpdateSku = vi.fn();
    render(
      <WithTheme>
        <ResultReviewActions
          result={{ ...baseResult, sku: '' }}
          actionLoading={false}
          onConfirm={vi.fn()}
          onUpdateQuantity={vi.fn()}
          onUpdateSku={onUpdateSku}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /Update SKU/i }));
    expect(screen.getByText(/SKU is required/i)).toBeInTheDocument();
    expect(onUpdateSku).not.toHaveBeenCalled();
  });

  it('disables confirm while action is pending', () => {
    render(
      <WithTheme>
        <ResultReviewActions
          result={baseResult}
          actionLoading
          onConfirm={vi.fn()}
          onUpdateQuantity={vi.fn()}
          onUpdateSku={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    expect(screen.getByRole('button', { name: /Sending/i })).toBeDisabled();
  });
});
