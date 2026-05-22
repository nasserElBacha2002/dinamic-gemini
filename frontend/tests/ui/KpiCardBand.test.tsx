import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../../src/theme';
import KpiCardBand from '../../src/components/ui/KpiCardBand';
import KpiCard from '../../src/components/ui/KpiCard';

describe('KpiCardBand', () => {
  it('renders children for flexStrip variant', () => {
    render(
      <ThemeProvider theme={theme}>
        <KpiCardBand variant="flexStrip">
          <KpiCard label="L1" value={1} />
        </KpiCardBand>
      </ThemeProvider>
    );
    expect(screen.getByText('L1')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders multiple KPI cards in responsiveGrid variant', () => {
    render(
      <ThemeProvider theme={theme}>
        <KpiCardBand variant="responsiveGrid">
          <KpiCard label="A" value="x" />
          <KpiCard label="B" value="y" />
        </KpiCardBand>
      </ThemeProvider>
    );
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
  });
});
