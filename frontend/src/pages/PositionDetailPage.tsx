/**
 * v3.3 — Deep link shim: `/positions/:positionId` redirects to the list view and opens the canonical review drawer.
 * No separate standalone review page.
 */

import { useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { parseResultDetailNavigationState } from '../features/results';
import { useInventoryDetail, useAislesList } from '../hooks';

export default function PositionDetailPage() {
  const { inventoryId, aisleId, positionId } = useParams<{
    inventoryId: string;
    aisleId: string;
    positionId: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const navState = useMemo(() => parseResultDetailNavigationState(location.state), [location.state]);
  const jobIdFromQuery = searchParams.get('jobId')?.trim() || null;
  const redirected = useRef(false);

  const invQ = useInventoryDetail(inventoryId, { enabled: Boolean(inventoryId) });
  const aislesQ = useAislesList(inventoryId, { enabled: Boolean(inventoryId) });

  useEffect(() => {
    if (redirected.current || !inventoryId || !aisleId || !positionId) return;
    if (!invQ.data?.name || !aislesQ.isFetched) return;

    const aisleCode = aislesQ.data?.items?.find((a) => a.id === aisleId)?.code ?? '—';
    const resultIds = navState?.resultIds ?? [positionId];
    redirected.current = true;

    if (navState?.returnTo === 'review_queue') {
      navigate('/review-queue', {
        replace: true,
        state: {
          openReviewDrawer: {
            kind: 'queue',
            inventoryId,
            aisleId,
            positionId,
            resultIds,
            inventoryName: invQ.data.name,
            aisleCode,
          },
        },
      });
      return;
    }

    const q = jobIdFromQuery ? `?jobId=${encodeURIComponent(jobIdFromQuery)}` : '';
    navigate(`/inventories/${inventoryId}/aisles/${aisleId}/positions${q}`, {
      replace: true,
      state: {
        openReviewDrawer: {
          kind: 'aisle',
          positionId,
          resultIds,
          filter: navState?.filter,
          jobId: jobIdFromQuery,
        },
      },
    });
  }, [
    inventoryId,
    aisleId,
    positionId,
    invQ.data?.name,
    aislesQ.data?.items,
    aislesQ.isFetched,
    navState,
    navigate,
    jobIdFromQuery,
  ]);

  if (!inventoryId || !aisleId || !positionId) {
    return (
      <>
        <Alert severity="warning">Missing inventory, aisle, or position.</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/inventories')}>
          Back to list
        </Button>
      </>
    );
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight={200} p={3}>
      <CircularProgress aria-label="Opening review" />
    </Box>
  );
}
