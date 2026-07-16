/**
 * View toggle: unmatched tab label + disabled when without_result === 0.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import JobImageResultsViewToggle from '../../../../src/features/results/components/imageCoverage/JobImageResultsViewToggle';

describe('JobImageResultsViewToggle', () => {
  it('enables images tab and shows pending count when without_result > 0', () => {
    render(
      <JobImageResultsViewToggle
        value="positions"
        withoutResultCount={13}
        imagesDisabled={false}
        onChange={vi.fn()}
      />
    );

    const imagesTab = screen.getByTestId('results-view-toggle-images');
    expect(imagesTab).not.toBeDisabled();
    expect(imagesTab).toHaveTextContent(/13/);
    expect(imagesTab).toHaveTextContent(/sin contar/i);
  });

  it('disables images tab when without_result === 0', () => {
    const onChange = vi.fn();
    render(
      <JobImageResultsViewToggle
        value="positions"
        withoutResultCount={0}
        imagesDisabled
        onChange={onChange}
      />
    );

    const imagesTab = screen.getByTestId('results-view-toggle-images');
    expect(imagesTab).toBeDisabled();
    fireEvent.click(imagesTab);
    expect(onChange).not.toHaveBeenCalled();
  });
});
