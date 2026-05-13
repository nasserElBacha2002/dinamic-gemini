/**
 * Legacy `/analytics/compare` URL → canonical compare-many.
 * Maps `jobAId`/`jobBId` query params to `jobIds` + `baseline` when possible.
 */

import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { ROUTE_HOME, pathToInventoryAnalyticsCompareMany } from '../../constants/appRoutes';

export default function AnalyticsCompareRedirect() {
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const [searchParams] = useSearchParams();

  if (!inventoryId) {
    return <Navigate to={ROUTE_HOME} replace />;
  }

  const base = pathToInventoryAnalyticsCompareMany(inventoryId);
  const aisleId = searchParams.get('aisleId')?.trim() ?? '';
  const jobA = searchParams.get('jobAId')?.trim() ?? '';
  const jobB = searchParams.get('jobBId')?.trim() ?? '';

  const next = new URLSearchParams();
  if (aisleId) next.set('aisleId', aisleId);
  if (jobA && jobB && jobA !== jobB) {
    next.set('jobIds', `${jobA},${jobB}`);
    next.set('baseline', jobA);
  }

  const qs = next.toString();
  return <Navigate to={qs ? `${base}?${qs}` : base} replace />;
}
