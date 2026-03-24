import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { PageLayout, LoadingBlock, EmptyState, ErrorAlert } from '../components/ui';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import { useInventoriesList, useCreateInventory } from '../hooks';
import { useAuth } from '../features/auth';

export default function InventoriesList() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useInventoriesList();
  const inventories: InventoryListItem[] = data ?? [];
  const createMutation = useCreateInventory();

  const errorMessage =
    isError && error ? (error instanceof ApiError ? getApiErrorMessage(error, 'Failed to load inventories') : String(error)) : null;

  const handleCreateSuccess = (created: Inventory) => {
    setCreateOpen(false);
    setCreateError(null);
    if (created.id) {
      navigate(`/inventories/${created.id}`);
    } else {
      refetch();
    }
  };

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h5">
          Dinamic Inventory v3
        </Typography>
        <Button variant="outlined" size="small" onClick={logout}>
          Logout
        </Button>
      </Box>

      {errorMessage && (
        <ErrorAlert message={errorMessage} onRetry={() => refetch()} />
      )}

      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
        <Button variant="contained" onClick={() => { setCreateError(null); setCreateOpen(true); }}>
          Create inventory
        </Button>
      </Box>

      {isLoading ? (
        <LoadingBlock />
      ) : inventories.length === 0 ? (
        <EmptyState message="No inventories yet. Create one to get started." padding={4} />
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {inventories.map((inv) => (
                <TableRow key={inv.id}>
                  <TableCell>{inv.name}</TableCell>
                  <TableCell>{inv.status}</TableCell>
                  <TableCell>{formatDate(inv.created_at ?? undefined)}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => navigate(`/inventories/${inv.id}`)}>
                      Open
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {createError && (
        <ErrorAlert
          message={createError}
          onRetry={() => { setCreateError(null); refetch(); }}
          onClose={() => setCreateError(null)}
        />
      )}

      <CreateInventoryDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={handleCreateSuccess}
        onError={setCreateError}
        createInventoryFn={createMutation.mutateAsync}
      />
    </PageLayout>
  );
}
