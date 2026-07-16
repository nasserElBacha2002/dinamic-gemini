/**
 * EvidencePreviewStage — no nested buttons (validateDOMNesting).
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import EvidencePreviewStage from '../../../../src/features/results/components/detail/EvidencePreviewStage';

describe('EvidencePreviewStage', () => {
  it('does not nest buttons (image button and fullscreen IconButton are siblings)', () => {
    render(
      <EvidencePreviewStage
        src="blob:http://localhost/img"
        alt="test"
        canOpenFullscreen
        onOpenFullscreen={vi.fn()}
      />
    );

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    for (const button of buttons) {
      expect(button.querySelector('button')).toBeNull();
    }

    const img = screen.getByTestId('evidence-preview-image');
    expect(img).toHaveStyle({ objectFit: 'contain', width: '100%' });
  });
});
