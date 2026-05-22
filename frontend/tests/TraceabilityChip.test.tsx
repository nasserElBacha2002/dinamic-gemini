/**
 * Epic 3.1.B — TraceabilityChip tests.
 * Covers each status and tooltip.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TraceabilityChip from '../src/components/ui/TraceabilityChip';

describe('TraceabilityChip', () => {
  it('renders non-misleading label for status valid', () => {
    render(<TraceabilityChip status="valid" />);
    expect(screen.getByText('ID presente en imágenes analizadas')).toBeInTheDocument();
    expect(screen.queryByText('Válida')).not.toBeInTheDocument();
  });

  it('renders label for status missing', () => {
    render(<TraceabilityChip status="missing" />);
    expect(screen.getByText('Sin ID de imagen')).toBeInTheDocument();
  });

  it('renders label for status invalid', () => {
    render(<TraceabilityChip status="invalid" />);
    expect(screen.getByText('ID no coincide con imágenes analizadas')).toBeInTheDocument();
    expect(screen.queryByText('Inválida')).not.toBeInTheDocument();
  });

  it('renders label for status unvalidated', () => {
    render(<TraceabilityChip status="unvalidated" />);
    expect(screen.getByText('No validado')).toBeInTheDocument();
  });

  it('shows tooltip when tooltip prop is provided', () => {
    render(
      <TraceabilityChip status="invalid" tooltip="Image not found in job" />
    );
    expect(screen.getByText('ID no coincide con imágenes analizadas')).toBeInTheDocument();
    expect(screen.getByLabelText('Image not found in job')).toBeInTheDocument();
  });

  it('uses small size by default', () => {
    const { container } = render(<TraceabilityChip status="valid" />);
    const chip = container.querySelector('.MuiChip-root');
    expect(chip).toHaveClass('MuiChip-sizeSmall');
  });
});
