import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Link } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
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
import { INVENTORY_LIST_EMPTY_MESSAGE_KEY, INVENTORY_LIST_EMPTY_TITLE_KEY } from '../constants/uiCopy';

export default function InventoriesList() {
  const { t } = useTranslation();
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
    isError && error
      ? error instanceof ApiError
        ? resolveApiErrorMessage(error, 'errors.load_inventories')
        : resolveApiErrorMessage(error, 'errors.load_inventories')
      : null;

  const handleCreateSuccess = (created: Inventory) => {
    setCreateOpen(false);
    setCreateError(null);
    showSnackbar(t('inventory.created_snackbar', { name: created.name }), 'success');
    void refetch();
    if (created.id) navigate(`/inventories/${created.id}`);
  };

  const columns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'name',
        label: t('inventory.column_inventory'),
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
        label: t('inventory.column_status'),
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
        label: t('common.created'),
        sortable: true,
        cell: (inv) => formatDate(inv.created_at ?? undefined),
      },
      {
        id: 'aisles_count',
        label: t('inventory.column_aisles'),
        sortable: true,
        align: 'right',
        cell: (inv) => (typeof inv.aisles_count === 'number' ? inv.aisles_count : t('common.em_dash')),
      },
      {
        id: 'pending_review_count',
        label: t('inventory.column_pending_review'),
        sortable: true,
        align: 'right',
        cell: (inv) => (typeof inv.pending_review_count === 'number' ? inv.pending_review_count : t('common.em_dash')),
      },
      {
        id: 'last_activity_at',
        label: t('common.last_activity'),
        sortable: true,
        cell: (inv) => formatDate(inv.last_activity_at ?? undefined),
      },
    ],
    [navigate, t]
  );

  return (
    <>
      <PageHeader
        a11yTitle={t('inventory.page_a11y')}
        actions={
          <Button
            variant="contained"
            onClick={() => {
              setCreateError(null);
              setCreateOpen(true);
            }}
          >
            {t('inventory.create')}
          </Button>
        }
      />

      {errorMessage && <ErrorAlert message={errorMessage} onRetry={() => refetch()} />}

      {!errorMessage ? (
      <SectionCard title={t('inventory.all_inventories')} subtitle={t('inventory.all_inventories_subtitle')}>
        <DataTable<InventoryListItem>
          rows={inventories}
          rowKey={(inv) => inv.id}
          columns={columns}
          loading={isLoading}
          emptyState={{
            title: t(INVENTORY_LIST_EMPTY_TITLE_KEY),
            message: t(INVENTORY_LIST_EMPTY_MESSAGE_KEY),
            action: (
              <Button
                variant="contained"
                onClick={() => {
                  setCreateError(null);
                  setCreateOpen(true);
                }}
              >
                {t('inventory.create')}
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
