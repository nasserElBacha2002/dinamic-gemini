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
  ErrorAlert,
  FilterToolbar,
  StatusBadge,
  TableSearchField,
  TableSection,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import { useDebouncedSearchInput, useInventoriesList, useCreateInventory, useTableState } from '../hooks';
import { DEFAULT_LIST_PAGE_SIZE, TABLE_SERVER_SEARCH_DEBOUNCE_MS } from '../constants/dataTable';
import { pathToInventory } from '../constants/appRoutes';
import { INVENTORY_LIST_EMPTY_MESSAGE_KEY, INVENTORY_LIST_EMPTY_TITLE_KEY } from '../constants/uiCopy';

const INVENTORY_LIST_INITIAL_SORT = { sortBy: 'created_at', sortDir: 'desc' as const };

export default function InventoriesList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const {
    page,
    pageSize,
    sortBy,
    sortDir,
    setPage,
    setPageSize,
    setSort,
    resetTableState,
  } = useTableState({
    initialPage: 1,
    initialPageSize: DEFAULT_LIST_PAGE_SIZE,
    initialSortBy: INVENTORY_LIST_INITIAL_SORT.sortBy,
    initialSortDir: INVENTORY_LIST_INITIAL_SORT.sortDir,
  });
  const {
    input: searchInput,
    setInput: setSearchInput,
    applied: searchApplied,
  } = useDebouncedSearchInput(TABLE_SERVER_SEARCH_DEBOUNCE_MS);

  const listQuery = useMemo(
    () => ({
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
      search: searchApplied || undefined,
    }),
    [page, pageSize, sortBy, sortDir, searchApplied]
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
    if (created.id) navigate(pathToInventory(created.id));
  };

  const columns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'name',
        label: t('inventory.column_inventory'),
        sortable: true,
        serverSortKey: 'name',
        cell: (inv) => (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.primary"
            sx={{ fontWeight: 600, textAlign: 'left' }}
            onClick={() => navigate(pathToInventory(inv.id))}
          >
            {inv.name}
          </Link>
        ),
      },
      {
        id: 'status',
        label: t('inventory.column_status'),
        sortable: true,
        serverSortKey: 'status',
        cell: (inv) => (
          <StatusBadge
            label={formatInventoryStatusLabel(String(inv.status))}
            semantic={inventoryStatusToBadgeSemantic(String(inv.status))}
          />
        ),
      },
      {
        id: 'processing_mode',
        label: t('dialogs.inventory.processing_mode_label'),
        sortable: false,
        cell: (inv) => {
          const isTest = inv.processing_mode === 'test';
          return (
            <StatusBadge
              label={isTest ? t('inventory.processing_mode_test') : t('inventory.processing_mode_production')}
              semantic={isTest ? 'warning' : 'neutral'}
            />
          );
        },
      },
      {
        id: 'created_at',
        label: t('common.created'),
        sortable: true,
        serverSortKey: 'created_at',
        cell: (inv) => formatDate(inv.created_at ?? undefined),
      },
      {
        id: 'aisles_count',
        label: t('inventory.column_aisles'),
        sortable: true,
        serverSortKey: 'aisles_count',
        align: 'right',
        cell: (inv) => (typeof inv.aisles_count === 'number' ? inv.aisles_count : t('common.em_dash')),
      },
      {
        id: 'pending_review_count',
        label: t('inventory.column_pending_review'),
        sortable: true,
        serverSortKey: 'pending_review_count',
        align: 'right',
        cell: (inv) => (typeof inv.pending_review_count === 'number' ? inv.pending_review_count : t('common.em_dash')),
      },
      {
        id: 'last_activity_at',
        label: t('common.last_activity'),
        sortable: true,
        serverSortKey: 'last_activity_at',
        cell: (inv) => formatDate(inv.last_activity_at ?? undefined),
      },
    ],
    [navigate, t]
  );

  const listErrorProps =
    errorMessage != null
      ? { error, context: 'inventory' as const, onRetry: () => refetch() }
      : null;

  return (
    <>
      <PageHeader
        a11yTitle={t('inventory.page_a11y')}
        primaryActions={
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

      <TableSection<InventoryListItem>
        testId="inventories-list-section"
        title={t('inventory.all_inventories')}
        description={t('inventory.all_inventories_subtitle')}
        error={listErrorProps}
        hideSectionOnError
        toolbar={
          <FilterToolbar
            primary={
              <TableSearchField
                value={searchInput}
                onChange={(value) => {
                  setSearchInput(value);
                  setPage(1);
                }}
                data-testid="inventories-list-search"
              />
            }
            onReset={() => {
              setSearchInput('');
              resetTableState();
            }}
            resetDisabled={
              searchInput === '' &&
              page === 1 &&
              pageSize === DEFAULT_LIST_PAGE_SIZE &&
              sortBy === INVENTORY_LIST_INITIAL_SORT.sortBy &&
              sortDir === INVENTORY_LIST_INITIAL_SORT.sortDir
            }
          />
        }
        table={{
          rows: inventories,
          rowKey: (inv) => inv.id,
          columns,
          loading: isLoading,
          onRowClick: (inv) => navigate(pathToInventory(inv.id)),
          mobile: {
            mode: 'card',
            title: (inv) => inv.name,
            status: (inv) => (
              <StatusBadge
                label={formatInventoryStatusLabel(String(inv.status))}
                semantic={inventoryStatusToBadgeSemantic(String(inv.status))}
              />
            ),
            ariaLabel: (inv) => inv.name,
            fields: [
              {
                id: 'processing_mode',
                label: t('dialogs.inventory.processing_mode_label'),
                value: (inv) => {
                  const isTest = inv.processing_mode === 'test';
                  return (
                    <StatusBadge
                      label={isTest ? t('inventory.processing_mode_test') : t('inventory.processing_mode_production')}
                      semantic={isTest ? 'warning' : 'neutral'}
                    />
                  );
                },
                fullWidth: true,
              },
              {
                id: 'aisles_count',
                label: t('inventory.column_aisles'),
                value: (inv) => (typeof inv.aisles_count === 'number' ? inv.aisles_count : t('common.em_dash')),
              },
              {
                id: 'pending_review_count',
                label: t('inventory.column_pending_review'),
                value: (inv) =>
                  typeof inv.pending_review_count === 'number' ? inv.pending_review_count : t('common.em_dash'),
              },
              {
                id: 'created_at',
                label: t('common.created'),
                value: (inv) => formatDate(inv.created_at ?? undefined),
                fullWidth: true,
              },
            ],
          },
          emptyState:
            searchApplied.trim() !== '' && !isLoading && (data?.total_items ?? 0) === 0
              ? { message: t('table.empty_no_match') }
              : {
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
                },
          sort: {
            sortBy,
            sortDir,
            onSortChange: setSort,
          },
          pagination: data
            ? {
                page,
                pageSize,
                totalItems: data.total_items,
                onPageChange: setPage,
                onPageSizeChange: setPageSize,
              }
            : undefined,
        }}
      />

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
