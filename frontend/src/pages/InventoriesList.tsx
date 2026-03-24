import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { LoadingBlock, EmptyState, ErrorAlert } from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import { useInventoriesList, useCreateInventory } from '../hooks';

export default function InventoriesList() {
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useInventoriesList();
  const inventories: InventoryListItem[] = data?.items ?? [];
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
    <>
      {/* Topbar shows “Inventories”; visible h1 is sr-only — see `layout/AppShell.tsx` + `PageHeader` docs. */}
      <PageHeader
        a11yTitle="Inventories"
        actions={
          <Button variant="contained" onClick={() => { setCreateError(null); setCreateOpen(true); }}>
            Create inventory
          </Button>
        }
      />

      {errorMessage && (
        <ErrorAlert message={errorMessage} onRetry={() => refetch()} />
      )}

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
    </>
  );
}
