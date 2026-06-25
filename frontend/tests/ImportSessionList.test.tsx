import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ImportSessionList from '../src/features/ingestionSessions/components/ImportSessionList';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('ImportSessionList', () => {
  it('renders table section with empty state when no sessions', () => {
    render(
      <ThemeProvider theme={theme}>
        <MemoryRouter>
          <ImportSessionList title="Sessions" sessions={[]} loading={false} onOpen={vi.fn()} />
        </MemoryRouter>
      </ThemeProvider>
    );
    expect(screen.getByTestId('import-session-list-section')).toBeInTheDocument();
    expect(screen.getByText('ingestion_sessions.empty.title')).toBeInTheDocument();
  });
});
