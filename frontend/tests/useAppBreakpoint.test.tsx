import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import { useAppBreakpoint } from '../src/hooks/useAppBreakpoint';

function wrapper({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={createTheme()}>{children}</ThemeProvider>;
}

describe('useAppBreakpoint', () => {
  it('returns breakpoint flags without throwing', () => {
    const { result } = renderHook(() => useAppBreakpoint(), { wrapper });
    expect(typeof result.current.isMdUp).toBe('boolean');
    expect(typeof result.current.isCompact).toBe('boolean');
    expect(result.current.isDesktopShell).toBe(result.current.isMdUp);
    expect(result.current.isMobileNav).toBe(!result.current.isMdUp);
  });
});
