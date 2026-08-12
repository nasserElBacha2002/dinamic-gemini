import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Button, Checkbox, DialogContentText, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { Inventory, InventoryListItem } from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { formatDate } from '../utils/formatDate';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';
import {
  ConfirmDialog,
  ErrorAlert,
  FilterToolbar,
  RelatedEntityCell,
  StatusBadge,
  TableSearchField,
  TableSection,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { PageHeader } from '../components/shell';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import {
  useDebouncedSearchInput,
  useInventoriesList,
  useCreateInventory,
  useSoftDeleteInventories,
  useTableState,
} from '../hooks';
import { DEFAULT_LIST_PAGE_SIZE, TABLE_SERVER_SEARCH_DEBOUNCE_MS } from '../constants/dataTable';
import { pathToClient, pathToInventory } from '../constants/appRoutes';
import { INVENTORY_LIST_EMPTY_MESSAGE_KEY, INVENTORY_LIST_EMPTY_TITLE_KEY } from '../constants/uiCopy';

const INVENTORY_LIST_INITIAL_SORT = { sortBy: 'created_at', sortDir: 'desc' as const };

export default function InventoriesList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
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
  const softDeleteMutation = useSoftDeleteInventories();

  useEffect(() => {
    setSelectedIds(new Set());
  }, [page, pageSize, sortBy, sortDir, searchApplied]);

  const pageIds = useMemo(() => inventories.map((inv) => inv.id), [inventories]);
  const selectedCount = selectedIds.size;
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const somePageSelected = pageIds.some((id) => selectedIds.has(id));

  const toggleOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllPage = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        for (const id of pageIds) next.delete(id);
      } else {
        for (const id of pageIds) next.add(id);
      }
      return next;
    });
  };

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

  const handleConfirmDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setDeleteError(null);
    try {
      await softDeleteMutation.mutateAsync(ids);
      setConfirmOpen(false);
      setSelectedIds(new Set());
      showSnackbar(t('inventory.deleted_snackbar', { count: ids.length }), 'success');
    } catch (err) {
      setDeleteError(resolveApiErrorMessage(err, 'inventory.delete_error'));
    }
  };

  const columns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'select',
        label: (
          <Checkbox
            size="small"
            checked={allPageSelected}
            indeterminate={somePageSelected && !allPageSelected}
            onChange={toggleAllPage}
            disabled={pageIds.length === 0 || isLoading}
            inputProps={{ 'aria-label': t('inventory.select_all_page') }}
            data-testid="inventories-select-all"
          />
        ),
        sortable: false,
        width: 48,
        cell: (inv) => (
          <span data-datatable-skip-row-click="" onClick={(e) => e.stopPropagation()}>
            <Checkbox
              size="small"
              checked={selectedIds.has(inv.id)}
              onChange={() => toggleOne(inv.id)}
              inputProps={{ 'aria-label': t('inventory.select_row', { name: inv.name }) }}
              data-testid={`inventories-select-${inv.id}`}
            />
          </span>
        ),
      },
      {
        id: 'name',
        label: t('inventory.column_inventory'),
        sortable: true,
        serverSortKey: 'name',
        cell: (inv) => (
          <LinkLikeName
            name={inv.name}
            onNavigate={() => navigate(pathToInventory(inv.id))}
          />
        ),
      },
      {
        id: 'client',
        label: t('inventory.column_client'),
        sortable: false,
        width: 180,
        cell: (inv) => (
          <RelatedEntityCell
            name={inv.client_name}
            emptyLabel={t('inventory.no_client')}
            to={inv.client_id ? pathToClient(inv.client_id) : null}
            testId={`inventory-client-cell-${inv.id}`}
          />
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
    [
      allPageSelected,
      isLoading,
      navigate,
      pageIds.length,
      selectedIds,
      somePageSelected,
      t,
    ]
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
          <Stack direction="row" spacing={1} alignItems="center">
            {selectedCount > 0 ? (
              <Typography variant="body2" color="text.secondary" data-testid="inventories-selected-count">
                {t('inventory.selected_count', { count: selectedCount })}
              </Typography>
            ) : null}
            <Button
              variant="outlined"
              color="error"
              disabled={selectedCount === 0 || softDeleteMutation.isPending}
              onClick={() => {
                setDeleteError(null);
                setConfirmOpen(true);
              }}
              data-testid="inventories-delete-selected"
            >
              {t('inventory.delete_selected')}
            </Button>
            <Button
              variant="contained"
              onClick={() => {
                setCreateError(null);
                setCreateOpen(true);
              }}
            >
              {t('inventory.create')}
            </Button>
          </Stack>
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
                id: 'select',
                label: t('inventory.select_column'),
                value: (inv) => (
                  <Checkbox
                    size="small"
                    checked={selectedIds.has(inv.id)}
                    onChange={() => toggleOne(inv.id)}
                    onClick={(e) => e.stopPropagation()}
                    inputProps={{ 'aria-label': t('inventory.select_row', { name: inv.name }) }}
                    data-testid={`inventories-select-mobile-${inv.id}`}
                  />
                ),
              },
              {
                id: 'client',
                label: t('inventory.column_client'),
                value: (inv) => inv.client_name?.trim() || t('inventory.no_client'),
                fullWidth: true,
              },
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

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => {
          if (softDeleteMutation.isPending) return;
          setConfirmOpen(false);
          setDeleteError(null);
        }}
        title={t('inventory.delete_confirm_title', { count: selectedCount })}
        description={
          <Box>
            <DialogContentText>
              {t('inventory.delete_confirm_body', { count: selectedCount })}
            </DialogContentText>
          </Box>
        }
        confirmLabel={t('inventory.delete_confirm_action')}
        confirmColor="error"
        loading={softDeleteMutation.isPending}
        confirmPendingLabel={t('common.working')}
        errorMessage={deleteError}
        onConfirm={() => void handleConfirmDelete()}
      />
    </>
  );
}

function LinkLikeName({ name, onNavigate }: { name: string; onNavigate: () => void }) {
  return (
    <Button
      variant="text"
      color="inherit"
      onClick={(e) => {
        e.stopPropagation();
        onNavigate();
      }}
      sx={{ fontWeight: 600, textAlign: 'left', justifyContent: 'flex-start', p: 0, minWidth: 0 }}
    >
      {name}
    </Button>
  );
}
