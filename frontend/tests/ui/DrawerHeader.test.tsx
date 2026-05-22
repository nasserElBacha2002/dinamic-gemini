import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider, Typography } from '@mui/material';
import theme from '../../src/theme';
import DrawerHeader from '../../src/components/ui/DrawerHeader';

describe('DrawerHeader', () => {
  it('renders overline, title, subtitle and invokes onClose from the close button', () => {
    const onClose = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <DrawerHeader
          closeLabel="Close drawer"
          onClose={onClose}
          overline={<Typography variant="overline">Over</Typography>}
          title={<Typography variant="h6">Drawer title</Typography>}
          subtitle={<Typography variant="body2">Drawer subtitle</Typography>}
        />
      </ThemeProvider>
    );
    expect(screen.getByText('Over')).toBeInTheDocument();
    expect(screen.getByText('Drawer title')).toBeInTheDocument();
    expect(screen.getByText('Drawer subtitle')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Close drawer'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
