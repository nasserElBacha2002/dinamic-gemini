import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../../../src/theme';
import CodeScanDetectionsTable from '../../../src/features/aisle-code-scans/components/CodeScanDetectionsTable';
import type { CodeScanDetection } from '../../../src/api/types/codeScans';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../../src/features/aisle-code-scans/components/CopyCodeValueButton', () => ({
  default: () => <button type="button">copy</button>,
}));

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanAssetPreviewButton', () => ({
  default: () => <button type="button">preview</button>,
}));

function makeDetection(index: number): CodeScanDetection {
  return {
    id: `det-${index}`,
    run_id: 'run-1',
    asset_id: `asset-${index}`,
    code_type: 'barcode',
    code_value: `CODE-${index}`,
    normalized_code_value: `CODE-${index}`,
    detection_status: 'detected',
    confidence: null,
    bounding_box_json: null,
    scanner_engine: 'pyzbar',
    created_at: '2026-05-20T12:00:05Z',
    metadata_json: null,
    matched_position_id: null,
    match_status: 'no_match',
    match_type: 'no_match',
    match_confidence: 0,
    match_metadata_json: null,
    matched_at: null,
  };
}

describe('CodeScanDetectionsTable pagination', () => {
  it('resets to page 1 when detections dataset shrinks after navigating to page 2', () => {
    const fullDetections = Array.from({ length: 30 }, (_, i) => makeDetection(i + 1));
    const shortDetections = Array.from({ length: 5 }, (_, i) => makeDetection(i + 1));
    const { rerender } = render(
      <ThemeProvider theme={theme}>
        <CodeScanDetectionsTable
          detections={fullDetections}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: /siguiente|next page/i }));
    expect(screen.getByText('CODE-26')).toBeInTheDocument();
    expect(screen.queryByText('CODE-1')).not.toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <CodeScanDetectionsTable
          detections={shortDetections}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    expect(screen.getByText('CODE-1')).toBeInTheDocument();
    expect(screen.getByText('CODE-5')).toBeInTheDocument();
    expect(screen.queryByText('CODE-26')).not.toBeInTheDocument();
  });
});
