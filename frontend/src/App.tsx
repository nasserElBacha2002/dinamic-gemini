import { useMemo } from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from './features/auth';
import LoginPage from './features/auth/LoginPage';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import PositionDetailPage from './pages/PositionDetailPage';
import ScreenPlaceholderPage from './pages/ScreenPlaceholderPage';

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
  const listEl = useMemo(() => <InventoriesList />, []);
  const detailEl = useMemo(() => <InventoryDetail />, []);
  const positionsEl = useMemo(() => <AislePositionsPage />, []);
  const positionDetailEl = useMemo(() => <PositionDetailPage />, []);
  const dashboardEl = useMemo(
    () => (
      <ScreenPlaceholderPage
        title="Dashboard"
        description="Operational summary (KPIs, attention, activity) — planned for v3.3."
      />
    ),
    [],
  );
  const reviewQueueEl = useMemo(
    () => (
      <ScreenPlaceholderPage
        title="Review queue"
        description="Cross-inventory prioritized results — planned for v3.3."
      />
    ),
    [],
  );
  const metricsEl = useMemo(
    () => (
      <ScreenPlaceholderPage
        title="Metrics / Analytics"
        description="Trends and performance — planned for v3.3."
      />
    ),
    [],
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
      <Route path="/" element={listEl} />
      <Route path="/dashboard" element={dashboardEl} />
      <Route path="/review-queue" element={reviewQueueEl} />
      <Route path="/metrics" element={metricsEl} />
      <Route path="/inventories/:inventoryId" element={detailEl} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions" element={positionsEl} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions/:positionId" element={positionDetailEl} />
    </Routes>
  );
}

export default App;
