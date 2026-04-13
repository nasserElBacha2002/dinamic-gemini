import { useMemo } from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from './features/auth';
import LoginPage from './features/auth/LoginPage';
import AppShell from './layout/AppShell';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import CompareRunsPage from './pages/analytics/CompareRunsPage';
import LegacyAisleCompareRedirect from './pages/analytics/LegacyAisleCompareRedirect';
import PositionDetailPage from './pages/PositionDetailPage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import MetricsPage from './pages/MetricsPage';
import AdminAiConfigPage from './pages/AdminAiConfigPage';
import RequireUsernameAdmin from './features/auth/RequireUsernameAdmin';

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
  const compareRunsEl = useMemo(() => <CompareRunsPage />, []);
  const legacyCompareRedirectEl = useMemo(() => <LegacyAisleCompareRedirect />, []);
  const positionDetailEl = useMemo(() => <PositionDetailPage />, []);
  const reviewQueueEl = useMemo(() => <ReviewQueuePage />, []);
  const metricsEl = useMemo(() => <MetricsPage />, []);
  const adminAiConfigEl = useMemo(
    () => (
      <RequireUsernameAdmin>
        <AdminAiConfigPage />
      </RequireUsernameAdmin>
    ),
    []
  );

  if (!initialized) {
    return <AuthLoading />;
  }
  if (!user && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }
  if (user && location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }

  return (
    <Routes>
      <Route path="/login" element={loginEl} />
      <Route path="/" element={shellEl}>
        <Route index element={listEl} />
        <Route path="inventories" element={listEl} />
        <Route path="review-queue" element={reviewQueueEl} />
        <Route path="metrics" element={metricsEl} />
        <Route path="admin/ai-config" element={adminAiConfigEl} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="settings" element={<Navigate to="/" replace />} />
        <Route path="inventories/:inventoryId" element={detailEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/positions" element={positionsEl} />
        <Route path="inventories/:inventoryId/analytics/compare" element={compareRunsEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/compare" element={legacyCompareRedirectEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/positions/:positionId" element={positionDetailEl} />
      </Route>
    </Routes>
  );
}

export default App;
