import { useMemo } from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { pathToInventory, ROUTE_HOME } from '../../../constants/appRoutes';

/**
 * Legacy import-session URLs redirect into Inventario → Pasillo (upload from aisle).
 * Backend capture-session APIs remain for compatibility; the UI no longer exposes "Sesiones".
 */
export default function IngestionSessionsLegacyRedirect() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [params] = useSearchParams();
  const inventoryId = (params.get('inventoryId') ?? '').trim();

  const to = useMemo(() => {
    if (inventoryId) {
      return pathToInventory(inventoryId);
    }
    return ROUTE_HOME;
  }, [inventoryId]);

  // sessionId retained only so old bookmarks still resolve; aisle upload lives on inventory detail.
  void sessionId;
  return <Navigate to={to} replace />;
}
