import { useMemo } from 'react';
import { Routes, Route } from 'react-router-dom';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import PositionDetailPage from './pages/PositionDetailPage';
import JobEntitiesPage from './pages/JobEntitiesPage';

/**
 * Route elements are memoized so that parent re-renders (e.g. Router context updates
 * after initial load) do not pass a new element reference. Without this, React would
 * unmount and remount the page component, causing TanStack Query to run the same
 * query twice (first observer unmounts/cancels, second observer mounts and fetches).
 */
function App() {
  const listEl = useMemo(() => <InventoriesList />, []);
  const detailEl = useMemo(() => <InventoryDetail />, []);
  const positionsEl = useMemo(() => <AislePositionsPage />, []);
  const positionDetailEl = useMemo(() => <PositionDetailPage />, []);
  const jobEntitiesEl = useMemo(() => <JobEntitiesPage />, []);

  return (
    <Routes>
      <Route path="/" element={listEl} />
      <Route path="/inventories/:inventoryId" element={detailEl} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions" element={positionsEl} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions/:positionId" element={positionDetailEl} />
      <Route path="/job-entities/:jobId" element={jobEntitiesEl} />
    </Routes>
  );
}

export default App;
