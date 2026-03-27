import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Link } from '@mui/material';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import {
  DataTable,
  ErrorAlert,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
  type DataTableColumn,
  type DataTableSortDirection,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import { useInventoriesList, useCreateInventory } from '../hooks';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { inventoryListEmpty } from '../constants/uiCopy';

export default function InventoriesList() {
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState<DataTableSortDirection>('desc');

  const listQuery = useMemo(
    () => ({
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
    }),
    [page, pageSize, sortBy, sortDir]
  );

  const { data, isLoading, isError, error, refetch } = useInventoriesList(listQuery);
  const inventories: InventoryListItem[] = data?.items ?? [];
  const createMutation = useCreateInventory();

  const errorMessage =
    isError && error ? (error instanceof ApiError ? getApiErrorMessage(error, 'Failed to load inventories') : String(error)) : null;

  const handleCreateSuccess = (created: Inventory) => {
    setCreateOpen(false);
    setCreateError(null);
    showSnackbar(`Inventory “${created.name}” created`, 'success');
    void refetch();
    if (created.id) navigate(`/inventories/${created.id}`);
  };

  const columns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'name',
        label: 'Inventory',
        sortable: true,
        cell: (inv) => (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.primary"
            sx={{ fontWeight: 600, textAlign: 'left' }}
            onClick={() => navigate(`/inventories/${inv.id}`)}
          >
            {inv.name}
          </Link>
        ),
      },
      {
        id: 'status',
        label: 'Status',
        sortable: true,
        cell: (inv) => (
          <StatusBadge
            label={formatInventoryStatusLabel(String(inv.status))}
            semantic={inventoryStatusToBadgeSemantic(String(inv.status))}
          />
        ),
      },
      {
        id: 'created_at',
        label: 'Created',
        sortable: true,
        cell: (inv) => formatDate(inv.created_at ?? undefined),
      },
      {
        id: 'aisles_count',
        label: 'Aisles',
        sortable: true,
        align: 'right',
        cell: (inv) => (typeof inv.aisles_count === 'number' ? inv.aisles_count : '—'),
      },
      {
        id: 'pending_review_count',
        label: 'Pending review',
        sortable: true,
        align: 'right',
        cell: (inv) => (typeof inv.pending_review_count === 'number' ? inv.pending_review_count : '—'),
      },
      {
        id: 'last_activity_at',
        label: 'Last activity',
        sortable: true,
        cell: (inv) => formatDate(inv.last_activity_at ?? undefined),
      },
    ],
    [navigate]
  );

  return (
    <>
      <PageHeader
        title="Inventories"
        subtitle="Manage inventories, aisles, processing, and review."
        actions={
          <Button
            variant="contained"
            onClick={() => {
              setCreateError(null);
              setCreateOpen(true);
            }}
          >
            Create inventory
          </Button>
        }
      />

      {errorMessage && <ErrorAlert message={errorMessage} onRetry={() => refetch()} />}

      {!errorMessage ? (
      <SectionCard title="All inventories" subtitle="Select an inventory to manage aisles, uploads, processing, and review.">
        <DataTable<InventoryListItem>
          rows={inventories}
          rowKey={(inv) => inv.id}
          columns={columns}
          loading={isLoading}
          emptyState={{
            title: inventoryListEmpty.title,
            message: inventoryListEmpty.message,
            action: (
              <Button
                variant="contained"
                onClick={() => {
                  setCreateError(null);
                  setCreateOpen(true);
                }}
              >
                Create inventory
              </Button>
            ),
          }}
          sort={{
            sortBy,
            sortDir,
            onSortChange: (sb, sd) => {
              setSortBy(sb);
              setSortDir(sd);
              setPage(1);
            },
          }}
          pagination={
            data
              ? {
                  page,
                  pageSize,
                  totalItems: data.total_items,
                  onPageChange: setPage,
                  /** Page reset to 1 on size change is handled inside `DataTable`. */
                  onPageSizeChange: setPageSize,
                }
              : undefined
          }
        />
      </SectionCard>
      ) : null}

      {createError && (
        <ErrorAlert
          message={createError}
          onRetry={() => {
            setCreateError(null);
            refetch();
          }}
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
