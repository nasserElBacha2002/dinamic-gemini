/**
 * Epic 3.1.B — TraceabilityChip tests.
 * Covers each status and tooltip.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TraceabilityChip from '../src/components/ui/TraceabilityChip';

describe('TraceabilityChip', () => {
  it('renders Valid label for status valid', () => {
    render(<TraceabilityChip status="valid" />);
    expect(screen.getByText('Valid')).toBeInTheDocument();
  });

  it('renders Missing label for status missing', () => {
    render(<TraceabilityChip status="missing" />);
    expect(screen.getByText('Missing')).toBeInTheDocument();
  });

  it('renders Invalid label for status invalid', () => {
    render(<TraceabilityChip status="invalid" />);
    expect(screen.getByText('Invalid')).toBeInTheDocument();
  });

  it('renders Unvalidated label for status unvalidated', () => {
    render(<TraceabilityChip status="unvalidated" />);
    expect(screen.getByText('Unvalidated')).toBeInTheDocument();
  });

  it('shows tooltip when tooltip prop is provided', () => {
    render(
      <TraceabilityChip status="invalid" tooltip="Image not found in job" />
    );
    expect(screen.getByText('Invalid')).toBeInTheDocument();
    expect(screen.getByLabelText('Image not found in job')).toBeInTheDocument();
  });

  it('uses small size by default', () => {
    const { container } = render(<TraceabilityChip status="valid" />);
    const chip = container.querySelector('.MuiChip-root');
    expect(chip).toHaveClass('MuiChip-sizeSmall');
  });
});
