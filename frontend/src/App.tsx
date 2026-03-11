import { Routes, Route } from 'react-router-dom';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';
import AislePositionsPage from './pages/AislePositionsPage';
import PositionDetailPage from './pages/PositionDetailPage';

function App() {
  return (
    <Routes>
      <Route path="/" element={<InventoriesList />} />
      <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions" element={<AislePositionsPage />} />
      <Route path="/inventories/:inventoryId/aisles/:aisleId/positions/:positionId" element={<PositionDetailPage />} />
    </Routes>
  );
}

export default App;
