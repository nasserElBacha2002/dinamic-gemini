import { useMemo } from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from './features/auth';
import LoginPage from './features/auth/LoginPage';
import AppShell from './layout/AppShell';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import AisleComparePage from './pages/AisleComparePage';
import PositionDetailPage from './pages/PositionDetailPage';
import DashboardPage from './pages/DashboardPage';
import ReviewQueuePage from './pages/ReviewQueuePage';
import MetricsPage from './pages/MetricsPage';
import SettingsPage from './pages/SettingsPage';

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
  const compareEl = useMemo(() => <AisleComparePage />, []);
  const positionDetailEl = useMemo(() => <PositionDetailPage />, []);
  const dashboardEl = useMemo(() => <DashboardPage />, []);
  const reviewQueueEl = useMemo(() => <ReviewQueuePage />, []);
  const metricsEl = useMemo(() => <MetricsPage />, []);
  const settingsEl = useMemo(() => <SettingsPage />, []);

  if (!initialized) {
    return <AuthLoading />;
  }
  if (!user && location.pathname !== '/login') {
    return <Navigate to="/login" replace />;
  }
  if (user && location.pathname === '/login') {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <Routes>
      <Route path="/login" element={loginEl} />
      <Route path="/" element={shellEl}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={dashboardEl} />
        <Route path="inventories" element={listEl} />
        <Route path="review-queue" element={reviewQueueEl} />
        <Route path="metrics" element={metricsEl} />
        <Route path="settings" element={settingsEl} />
        <Route path="inventories/:inventoryId" element={detailEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/positions" element={positionsEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/compare" element={compareEl} />
        <Route path="inventories/:inventoryId/aisles/:aisleId/positions/:positionId" element={positionDetailEl} />
      </Route>
    </Routes>
  );
}

export default App;
