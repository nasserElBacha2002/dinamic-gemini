import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import IngestionSessionsLegacyRedirect from '../src/features/ingestionSessions/pages/IngestionSessionsLegacyRedirect';

describe('IngestionSessionsLegacyRedirect', () => {
  it('redirects session detail with inventoryId to inventory detail', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/ingestion-sessions/sess-1?inventoryId=inv-9']}>
        <Routes>
          <Route path="/ingestion-sessions/:sessionId" element={<IngestionSessionsLegacyRedirect />} />
          <Route path="/inventories/:inventoryId" element={<div data-testid="inv">inventory</div>} />
          <Route path="/" element={<div data-testid="home">home</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(container.querySelector('[data-testid="inv"]')).toBeTruthy();
  });

  it('redirects list route to home inventories when no inventory context', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/ingestion-sessions']}>
        <Routes>
          <Route path="/ingestion-sessions" element={<IngestionSessionsLegacyRedirect />} />
          <Route path="/" element={<div data-testid="home">home</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(container.querySelector('[data-testid="home"]')).toBeTruthy();
  });
});
