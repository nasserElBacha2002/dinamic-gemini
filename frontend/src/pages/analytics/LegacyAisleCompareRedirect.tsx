/**
 * Backward compatibility: old aisle-scoped compare URL → analytics compare with query params.
 */

import { Navigate, useParams, useSearchParams } from 'react-router-dom';

export default function LegacyAisleCompareRedirect() {
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const [searchParams] = useSearchParams();
  const jobAId = searchParams.get('jobAId')?.trim() || '';
  const jobBId = searchParams.get('jobBId')?.trim() || '';

  if (!inventoryId || !aisleId) {
    return <Navigate to="/" replace />;
  }

  const next = new URLSearchParams();
  next.set('aisleId', aisleId);
  if (jobAId) next.set('jobAId', jobAId);
  if (jobBId) next.set('jobBId', jobBId);

  return <Navigate to={`/inventories/${inventoryId}/analytics/compare?${next.toString()}`} replace />;
}
