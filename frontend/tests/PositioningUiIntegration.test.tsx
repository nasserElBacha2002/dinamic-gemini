/**
 * Physical-locations UI entry points removed; path helpers remain for legacy redirects.
 */

import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import {
  pathToAisleLocations,
  pathToClient,
  pathToClientPhysicalLocations,
  pathToInventory,
  pathToInventoryPhysicalLocations,
} from '../src/constants/appRoutes';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe('physical locations UI removed', () => {
  it('keeps legacy path helpers for redirects', () => {
    expect(pathToInventoryPhysicalLocations('inv-1')).toBe('/inventories/inv-1/posiciones-fisicas');
    expect(pathToInventory('inv-1')).toBe('/inventories/inv-1');
    expect(pathToAisleLocations('inv-1', 'aisle-1')).toBe(
      '/inventories/inv-1/aisles/aisle-1/locations'
    );
    expect(pathToClientPhysicalLocations('client-1')).toBe('/clientes/client-1/posiciones-fisicas');
    expect(pathToClient('client-1')).toBe('/clientes/client-1');
  });

  it('can redirect inventory physical-locations URL to inventory detail', async () => {
    render(
      <MemoryRouter initialEntries={[pathToInventoryPhysicalLocations('inv-1')]}>
        <Routes>
          <Route
            path="/inventories/:inventoryId/posiciones-fisicas"
            element={<Navigate to={pathToInventory('inv-1')} replace />}
          />
          <Route path="/inventories/:inventoryId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(pathToInventory('inv-1'));
    });
  });
});
