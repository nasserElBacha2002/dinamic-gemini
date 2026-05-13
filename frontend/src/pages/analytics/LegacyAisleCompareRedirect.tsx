/**
 * Backward compatibility: old aisle-scoped compare URL → analytics compare with query params.
 */

import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { ROUTE_HOME, pathToInventoryAnalyticsCompareMany } from '../../constants/appRoutes';

export default function LegacyAisleCompareRedirect() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const [searchParams] = useSearchParams();
  const jobAId = searchParams.get('jobAId')?.trim() || '';
  const jobBId = searchParams.get('jobBId')?.trim() || '';

  if (!inventoryId || !aisleId) {
    return <Navigate to={ROUTE_HOME} replace />;
  }

  const next = new URLSearchParams();
  next.set('aisleId', aisleId);
  if (jobAId && jobBId && jobAId !== jobBId) {
    next.set('jobIds', `${jobAId},${jobBId}`);
    next.set('baseline', jobAId);
  }

  const base = pathToInventoryAnalyticsCompareMany(inventoryId);
  const qs = next.toString();
  return <Navigate to={qs ? `${base}?${qs}` : base} replace />;
}
