/**
 * Phase 4.8 — ResultEvidenceDetails audit panel tests.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultEvidenceDetails from '../src/features/results/components/detail/ResultEvidenceDetails';
import type { ResultEvidenceView } from '../src/features/results/types';

function renderDetails(
  props: React.ComponentProps<typeof ResultEvidenceDetails>
) {
  return render(
    <ThemeProvider theme={theme}>
      <ResultEvidenceDetails {...props} />
    </ThemeProvider>
  );
}

function sampleEvidenceView(overrides: Partial<ResultEvidenceView> = {}): ResultEvidenceView {
  return {
    displayable: false,
    traceabilityStatus: 'invalid',
    traceabilityWarning: 'Returned image ID was not part of the final provider payload.',
    resolvedManifestEntryId: 'resolved-1',
    rawManifestEntryId: 'raw-1',
    provider: 'gemini',
    modelName: 'gemini-2.0',
    sourceKind: 'structural_result_evidence',
    imageAccessStatus: 'url_unavailable',
    ...overrides,
  };
}

describe('ResultEvidenceDetails', () => {
  it('renders nothing when evidenceView and artifactStatus are absent', () => {
    const { container } = renderDetails({ evidenceView: null });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders traceability audit rows from evidenceView', () => {
    renderDetails({ evidenceView: sampleEvidenceView() });

    expect(screen.getByText(/detalle de trazabilidad|traceability detail/i)).toBeInTheDocument();
    expect(screen.getByText('invalid')).toBeInTheDocument();
    expect(
      screen.getByText(/Returned image ID was not part of the final provider payload/i)
    ).toBeInTheDocument();
    expect(screen.getByText('resolved-1')).toBeInTheDocument();
    expect(screen.getByText('raw-1')).toBeInTheDocument();
    expect(screen.getByText('gemini')).toBeInTheDocument();
    expect(screen.getByText('gemini-2.0')).toBeInTheDocument();
    expect(screen.getByText('structural_result_evidence')).toBeInTheDocument();
    expect(screen.getByText('url_unavailable')).toBeInTheDocument();
  });

  it('renders artifact status when passed without evidenceView', () => {
    renderDetails({ evidenceView: null, artifactStatus: 'published' });
    expect(screen.getByText('published')).toBeInTheDocument();
  });

  it('renders artifact status alongside evidenceView fields', () => {
    renderDetails({
      evidenceView: sampleEvidenceView({ traceabilityWarning: null }),
      artifactStatus: 'missing',
    });
    expect(screen.getByText('missing')).toBeInTheDocument();
    expect(screen.getByText('invalid')).toBeInTheDocument();
  });
});
