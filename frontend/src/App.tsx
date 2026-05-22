import { useMemo } from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { ROUTE_HOME, ROUTE_LOGIN, ROUTE_PATH } from './constants/appRoutes';
import MetricsLegacyRedirect from './pages/analytics/MetricsLegacyRedirect';
import ObservabilityLegacyRedirect from './pages/analytics/ObservabilityLegacyRedirect';
import AisleObservabilityPage from './pages/AisleObservabilityPage';
import { useAuth } from './features/auth';
import LoginPage from './features/auth/LoginPage';
import AppShell from './layout/AppShell';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import CompareManyRunsPage from './pages/analytics/CompareManyRunsPage';
import AnalyticsCompareRedirect from './pages/analytics/AnalyticsCompareRedirect';
import LegacyAisleCompareRedirect from './pages/analytics/LegacyAisleCompareRedirect';
import PositionDetailPage from './pages/PositionDetailPage';
import ReviewQueueRedirect from './pages/ReviewQueueRedirect';
import AnalyticsDashboardPage from './pages/AnalyticsDashboardPage';
import ClientsList from './pages/ClientsList';
import ClientDetail from './pages/ClientDetail';
import ClientSupplierDetail from './pages/ClientSupplierDetail';
import AdminAiConfigPage from './pages/AdminAiConfigPage';
import RequireUsernameAdmin from './features/auth/RequireUsernameAdmin';
import IngestionSessionsPage from './features/ingestionSessions/pages/IngestionSessionsPage';
import IngestionSessionDetailPage from './features/ingestionSessions/pages/IngestionSessionDetailPage';

/** Minimal full-screen loading while auth bootstrap runs. */
function AuthLoading() {
  return (
    <Box display="flex" alignItems="center" justifyContent="center" minHeight="100vh">
      <CircularProgress />
    </Box>
  );
}

/**
 * Route elements are memoized so that parent re-renders (e.g. Router context updates
 * after initial load) do not pass a new element reference. Without this, React would
 * unmount and remount the page component, causing TanStack Query to run the same
 * query twice (first observer unmounts/cancels, second observer mounts and fetches).
 */
function App() {
  const { initialized, user } = useAuth();
  const location = useLocation();

  const loginEl = useMemo(() => <LoginPage />, []);
  const shellEl = useMemo(() => <AppShell />, []);
  const listEl = useMemo(() => <InventoriesList />, []);
  const detailEl = useMemo(() => <InventoryDetail />, []);
  const positionsEl = useMemo(() => <AislePositionsPage />, []);
  const compareManyRunsEl = useMemo(() => <CompareManyRunsPage />, []);
  const analyticsCompareRedirectEl = useMemo(() => <AnalyticsCompareRedirect />, []);
  const legacyCompareRedirectEl = useMemo(() => <LegacyAisleCompareRedirect />, []);
  const positionDetailEl = useMemo(() => <PositionDetailPage />, []);
  const reviewQueueRedirectEl = useMemo(() => <ReviewQueueRedirect />, []);
  const analyticsDashboardEl = useMemo(() => <AnalyticsDashboardPage />, []);
  const metricsLegacyRedirectEl = useMemo(() => <MetricsLegacyRedirect />, []);
  const observabilityLegacyRedirectEl = useMemo(() => <ObservabilityLegacyRedirect />, []);
  const clientsEl = useMemo(() => <ClientsList />, []);
  const clientDetailEl = useMemo(() => <ClientDetail />, []);
  const clientSupplierDetailEl = useMemo(() => <ClientSupplierDetail />, []);
  const adminAiConfigEl = useMemo(
    () => (
      <RequireUsernameAdmin>
        <AdminAiConfigPage />
      </RequireUsernameAdmin>
    ),
    []
  );
  const ingestionSessionsEl = useMemo(() => <IngestionSessionsPage />, []);
  const ingestionSessionDetailEl = useMemo(() => <IngestionSessionDetailPage />, []);
  const aisleObservabilityEl = useMemo(() => <AisleObservabilityPage />, []);
  if (!initialized) {
    return <AuthLoading />;
  }
  if (!user && location.pathname !== ROUTE_LOGIN) {
    return <Navigate to={ROUTE_LOGIN} replace />;
  }
  if (user && location.pathname === ROUTE_LOGIN) {
    return <Navigate to={ROUTE_HOME} replace />;
  }

  return (
    <Routes>
      <Route path={ROUTE_LOGIN} element={loginEl} />
      <Route path={ROUTE_HOME} element={shellEl}>
        <Route index element={listEl} />
        <Route path={ROUTE_PATH.inventories} element={listEl} />
        <Route path={ROUTE_PATH.reviewQueue} element={reviewQueueRedirectEl} />
        <Route path={ROUTE_PATH.metrics} element={metricsLegacyRedirectEl} />
        <Route path={ROUTE_PATH.analitica} element={analyticsDashboardEl} />
        <Route path={ROUTE_PATH.clients} element={clientsEl} />
        <Route path={ROUTE_PATH.clientSupplierDetail} element={clientSupplierDetailEl} />
        <Route path={ROUTE_PATH.clientDetail} element={clientDetailEl} />
        <Route path={ROUTE_PATH.ingestionSessions} element={ingestionSessionsEl} />
        <Route path={ROUTE_PATH.ingestionSessionDetail} element={ingestionSessionDetailEl} />
        <Route path={ROUTE_PATH.adminAiConfig} element={adminAiConfigEl} />
        <Route path={ROUTE_PATH.dashboard} element={<Navigate to={ROUTE_HOME} replace />} />
        <Route path={ROUTE_PATH.settings} element={<Navigate to={ROUTE_HOME} replace />} />
        <Route path={ROUTE_PATH.observabilidad} element={observabilityLegacyRedirectEl} />
        <Route path={ROUTE_PATH.inventoryDetail} element={detailEl} />
        <Route path={ROUTE_PATH.aislePositions} element={positionsEl} />
        <Route path={ROUTE_PATH.analyticsCompare} element={analyticsCompareRedirectEl} />
        <Route path={ROUTE_PATH.analyticsCompareMany} element={compareManyRunsEl} />
        <Route path={ROUTE_PATH.legacyAisleCompare} element={legacyCompareRedirectEl} />
        <Route path={ROUTE_PATH.positionDetail} element={positionDetailEl} />
        <Route path={ROUTE_PATH.aisleObservability} element={aisleObservabilityEl} />
      </Route>
    </Routes>
  );
}

export default App;
