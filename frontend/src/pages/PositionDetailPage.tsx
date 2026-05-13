/**
 * v3.3 — Deep link shim: `/positions/:positionId` redirects to the list view and opens the canonical review drawer.
 * No separate standalone review page.
 */

import { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { ROUTE_HOME, pathToAislePositions } from '../constants/appRoutes';
import { parseResultDetailNavigationState } from '../features/results';
import { useInventoryDetail, useAislesList } from '../hooks';

export default function PositionDetailPage() {
  const { t } = useTranslation();
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

    const rawIds = navState?.resultIds;
    const resultIds =
      Array.isArray(rawIds) && rawIds.length > 0 ? rawIds : [positionId];

    redirected.current = true;

    const q = jobIdFromQuery ? `?jobId=${encodeURIComponent(jobIdFromQuery)}` : '';
    navigate(`${pathToAislePositions(inventoryId, aisleId)}${q}`, {
      replace: true,
      state: {
        openReviewDrawer: {
          kind: 'aisle',
          positionId,
          resultIds,
          filter: navState?.filter,
          jobId: jobIdFromQuery,
          exactPositionDetail: true,
        },
      },
    });
    // One-shot redirect: `redirected` prevents duplicate navigations if aisle list refetches.
  }, [
    inventoryId,
    aisleId,
    positionId,
    invQ.data?.name,
    aislesQ.isFetched,
    navState,
    navigate,
    jobIdFromQuery,
  ]);

  if (!inventoryId || !aisleId || !positionId) {
    return (
      <>
        <Alert severity="warning">{t('positions.missing_params')}</Alert>
        <Button sx={{ mt: 2 }} onClick={() => navigate(ROUTE_HOME)}>
          {t('inventory.back_to_list')}
        </Button>
      </>
    );
  }

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight={200} p={3}>
      <CircularProgress aria-label={t('positions.opening_review')} />
    </Box>
  );
}
