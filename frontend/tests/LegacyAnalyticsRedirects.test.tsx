import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import MetricsLegacyRedirect from '../src/pages/analytics/MetricsLegacyRedirect';
import ObservabilityLegacyRedirect from '../src/pages/analytics/ObservabilityLegacyRedirect';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{`${location.pathname}${location.search}`}</div>;
}

describe('Legacy analytics redirects', () => {
  it('MetricsLegacyRedirect targets Calidad tab', () => {
    render(
      <MemoryRouter initialEntries={['/metrics']}>
        <Routes>
          <Route path="/metrics" element={<MetricsLegacyRedirect />} />
          <Route path="/analitica" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=calidad');
  });

  it('ObservabilityLegacyRedirect targets Proveedores tab', () => {
    render(
      <MemoryRouter initialEntries={['/observabilidad']}>
        <Routes>
          <Route path="/observabilidad" element={<ObservabilityLegacyRedirect />} />
          <Route path="/analitica" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/analitica?tab=proveedores');
  });
});
