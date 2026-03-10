import { Routes, Route } from 'react-router-dom';
import InventoriesList from './pages/InventoriesList';
import InventoryDetail from './pages/InventoryDetail';

function App() {
  return (
    <Routes>
      <Route path="/" element={<InventoriesList />} />
      <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
    </Routes>
  );
}

export default App;
