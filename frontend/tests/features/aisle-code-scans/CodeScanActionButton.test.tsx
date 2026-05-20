import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CodeScanActionButton from '../../../src/features/aisle-code-scans/components/CodeScanActionButton';

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanDrawer', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div data-testid="code-scan-drawer-open">drawer</div> : null,
}));

vi.mock('../../../src/features/aisle-code-scans/hooks/useRunAisleCodeScan', () => ({
  useRunAisleCodeScan: () => ({ isPending: false }),
}));

describe('CodeScanActionButton', () => {
  it('renders Escanear códigos and opens drawer', () => {
    render(<CodeScanActionButton inventoryId="inv-1" aisleId="aisle-1" />);
    expect(screen.getByTestId('aisle-code-scan-open')).toHaveTextContent(/Escanear códigos/i);
    fireEvent.click(screen.getByTestId('aisle-code-scan-open'));
    expect(screen.getByTestId('code-scan-drawer-open')).toBeInTheDocument();
  });
});
