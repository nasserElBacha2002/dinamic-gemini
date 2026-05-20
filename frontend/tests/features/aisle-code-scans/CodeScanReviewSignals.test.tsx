import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CodeScanReviewSignals from '../../../src/features/aisle-code-scans/components/CodeScanReviewSignals';

const useAisleCodeScanReviewSignals = vi.hoisted(() => vi.fn());

vi.mock('../../../src/features/aisle-code-scans/hooks/useAisleCodeScanReviewSignals', () => ({
  useAisleCodeScanReviewSignals,
}));

function renderSignals(
  hookReturn: Partial<ReturnType<typeof useAisleCodeScanReviewSignals>> = {}
) {
  useAisleCodeScanReviewSignals.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...hookReturn,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CodeScanReviewSignals inventoryId="inv-1" aisleId="aisle-1" enabled />
    </QueryClientProvider>
  );
}

describe('CodeScanReviewSignals', () => {
  beforeEach(() => {
    useAisleCodeScanReviewSignals.mockReset();
  });

  it('renders section title', () => {
    renderSignals();
    expect(screen.getByText('Señales de revisión')).toBeInTheDocument();
  });

  it('shows empty state', () => {
    renderSignals({
      data: {
        latest_run: null,
        summary: {
          total_signals: 0,
          info: 0,
          warning: 0,
          attention: 0,
          unmatched_codes: 0,
          multiple_candidates: 0,
          matched_codes: 0,
        },
        signals: [],
      },
    });
    expect(screen.getByText('No hay señales de revisión para este escaneo.')).toBeInTheDocument();
  });

  it('shows attention signal message', () => {
    renderSignals({
      data: {
        latest_run: null,
        summary: {
          total_signals: 1,
          info: 0,
          warning: 0,
          attention: 1,
          unmatched_codes: 1,
          multiple_candidates: 0,
          matched_codes: 0,
        },
        signals: [
          {
            id: 's1',
            type: 'code_no_match',
            severity: 'attention',
            message: 'Código detectado sin resultado vinculado.',
            detection_id: 'd1',
            position_id: null,
            asset_id: 'a1',
            code_value: '123',
            code_type: 'barcode',
          },
        ],
      },
    });
    expect(screen.getByText('Código detectado sin resultado vinculado.')).toBeInTheDocument();
    const section = screen.getByTestId('code-scan-review-signals');
    expect(section.textContent).not.toMatch(/Validado/i);
    expect(section.textContent).not.toMatch(/Confirmado/i);
  });
});
