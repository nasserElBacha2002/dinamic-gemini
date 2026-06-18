/**
 * Phase 4.2 corrections — ResultEvidencePanel evidence gating and stale preview cleanup.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultEvidencePanel from '../src/features/results/components/detail/ResultEvidencePanel';
import type { ResultDetail } from '../src/features/results/types';
import { useEvidenceImageLoad } from '../src/features/results/hooks/useEvidenceImageLoad';

vi.mock('../src/features/results/hooks/useEvidenceImageLoad', () => ({
  useEvidenceImageLoad: vi.fn(() => ({ status: 'idle' as const })),
}));

const mockUseEvidenceImageLoad = vi.mocked(useEvidenceImageLoad);

function baseResult(overrides: Partial<ResultDetail> = {}): ResultDetail {
  return {
    id: 'pos-1',
    sku: 'SKU-1',
    positionCode: 'P1',
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: 1,
    systemQty: 1,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    sourceImageId: 'asset-1',
    sourceFileName: 'photo.jpg',
    hasValidEvidence: true,
    evidence: [],
    reviewHistory: [],
    technicalMetadata: { entityId: 'job-1_E1' },
    ...overrides,
  };
}

function renderPanel(result: ResultDetail, props: { inventoryId?: string; aisleId?: string } = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <ResultEvidencePanel
        result={result}
        inventoryId={props.inventoryId ?? 'inv-1'}
        aisleId={props.aisleId ?? 'aisle-1'}
      />
    </ThemeProvider>
  );
}

const INVALID_MSG = /could not be validated|no se pudo validar la evidencia/i;
const MISSING_MSG = /no evidence image was returned|no devolvió una imagen de evidencia/i;
const UNVALIDATED_MSG = /traceability could not be confirmed|no se pudo confirmar la trazabilidad/i;

describe('ResultEvidencePanel', () => {
  beforeEach(() => {
    mockUseEvidenceImageLoad.mockReset();
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' });
  });

  it('VALID + hasValidEvidence + sourceImageId allows image loading and preview UI', () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:test-image',
    });

    renderPanel(baseResult());

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(
      expect.objectContaining({ assetId: 'asset-1', inventoryId: 'inv-1', aisleId: 'aisle-1' })
    );
    expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:test-image');
  });

  it('INVALID + sourceImageId does not render image and passes null spec to hook', () => {
    renderPanel(
      baseResult({
        traceabilityStatus: 'INVALID',
        hasValidEvidence: true,
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'asset-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(INVALID_MSG)).toBeInTheDocument();
  });

  it('MISSING shows missing message and no image', () => {
    renderPanel(
      baseResult({
        traceabilityStatus: 'MISSING',
        sourceImageId: null,
        hasValidEvidence: false,
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(MISSING_MSG)).toBeInTheDocument();
  });

  it('UNVALIDATED shows unvalidated message and no image', () => {
    renderPanel(
      baseResult({
        traceabilityStatus: 'UNVALIDATED',
        hasValidEvidence: false,
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(UNVALIDATED_MSG)).toBeInTheDocument();
  });

  it('VALID + hasValidEvidence false does not render image', () => {
    renderPanel(
      baseResult({
        hasValidEvidence: false,
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('Phase 4.8: evidenceView.displayable=false blocks image even with legacy-valid fields', () => {
    renderPanel(
      baseResult({
        traceabilityStatus: 'VALID',
        hasValidEvidence: true,
        sourceImageId: 'asset-1',
        evidenceView: {
          displayable: false,
          traceabilityStatus: 'invalid',
          sourceKind: 'structural_result_evidence',
        },
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('Phase 4.8: evidenceView.displayable=true allows image regardless of legacy flags', () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:structural',
    });

    renderPanel(
      baseResult({
        traceabilityStatus: 'INVALID',
        hasValidEvidence: false,
        sourceImageId: 'asset-1',
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          sourceImageId: 'asset-1',
        },
      })
    );

    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(
      expect.objectContaining({ assetId: 'asset-1' })
    );
    expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:structural');
  });

  it('clears preview when transitioning VALID to INVALID', async () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:test-image',
    });

    const { rerender } = renderPanel(baseResult());
    expect(screen.getByRole('img')).toBeInTheDocument();

    const viewButton = screen.getByRole('button', {
      name: /view full image|ver imagen completa|vista completa de la imagen/i,
    });
    fireEvent.click(viewButton);

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidencePanel
          result={baseResult({ traceabilityStatus: 'INVALID', hasValidEvidence: false })}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });
    expect(screen.getByText(INVALID_MSG)).toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenLastCalledWith(null);
  });

  it('clears preview when transitioning VALID to MISSING', () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:test-image',
    });

    const { rerender } = renderPanel(baseResult());
    expect(screen.getByRole('img')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidencePanel
          result={baseResult({
            traceabilityStatus: 'MISSING',
            sourceImageId: null,
            hasValidEvidence: false,
          })}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(MISSING_MSG)).toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenLastCalledWith(null);
  });
});
