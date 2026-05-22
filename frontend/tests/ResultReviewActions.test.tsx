/**
 * Sprint 5.2 — inline validation for review corrections.
 */

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
  positionCode: null,
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
          onUpdatePositionCode={vi.fn()}
          onMarkImageMismatch={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /corregir cantidad|correct quantity/i }));
    const qtyInput = screen.getByPlaceholderText(/qty placeholder|cantidad/i);
    fireEvent.change(qtyInput, { target: { value: '-1' } });
    expect(qtyInput).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: /guardar|save/i })).toBeDisabled();
    expect(onUpdateQuantity).not.toHaveBeenCalled();
  });

  it('disables SKU update when SKU is empty and shows hint', () => {
    const onUpdateSku = vi.fn();
    render(
      <WithTheme>
        <ResultReviewActions
          result={{ ...baseResult, sku: '' }}
          actionLoading={false}
          onConfirm={vi.fn()}
          onUpdateQuantity={vi.fn()}
          onUpdateSku={onUpdateSku}
          onUpdatePositionCode={vi.fn()}
          onMarkImageMismatch={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /corregir sku|correct sku/i }));
    expect(screen.getByRole('button', { name: /guardar|save/i })).toBeDisabled();
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
          onUpdatePositionCode={vi.fn()}
          onMarkImageMismatch={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    expect(screen.getByRole('button', { name: /confirmando|confirming/i })).toBeDisabled();
  });

  it('readOnly shows non-operational message and hides confirm', () => {
    render(
      <WithTheme>
        <ResultReviewActions
          result={baseResult}
          readOnly
          actionLoading={false}
          onConfirm={vi.fn()}
          onUpdateQuantity={vi.fn()}
          onUpdateSku={vi.fn()}
          onUpdatePositionCode={vi.fn()}
          onMarkImageMismatch={vi.fn()}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    expect(screen.getByText(/modo lectura|readonly run/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirmar resultado|confirm result/i })).toBeNull();
  });

  it('Wrong image calls onMarkImageMismatch', () => {
    const onMarkImageMismatch = vi.fn();
    render(
      <WithTheme>
        <ResultReviewActions
          result={baseResult}
          actionLoading={false}
          onConfirm={vi.fn()}
          onUpdateQuantity={vi.fn()}
          onUpdateSku={vi.fn()}
          onUpdatePositionCode={vi.fn()}
          onMarkImageMismatch={onMarkImageMismatch}
          onDeleteClick={vi.fn()}
        />
      </WithTheme>
    );
    fireEvent.click(screen.getByRole('button', { name: /imagen incorrecta|wrong image/i }));
    expect(onMarkImageMismatch).toHaveBeenCalledTimes(1);
  });
});
