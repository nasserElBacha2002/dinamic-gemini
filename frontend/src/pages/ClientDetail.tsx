import { useMemo, useState } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import type { ClientSupplier, InventoryListItem } from '../api/types';
import CreateClientSupplierDialog from '../components/CreateClientSupplierDialog';
import CreateInventoryDialog from '../components/CreateInventoryDialog';
import LabelGeneratorDialog from '../features/clients/components/LabelGeneratorDialog';
import { PageHeader } from '../components/shell';
import {
  DataTable,
  EmptyState,
  ErrorAlert,
  LoadingBlock,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
  sortDataTableRows,
  type DataTableColumn,
} from '../components/ui';
import { ROUTE_CLIENTS, pathToClientSupplier, pathToInventory } from '../constants/appRoutes';
import {
  useClient,
  useClientSuppliers,
  useCreateClientSupplier,
  useCreateInventory,
  useInventoriesList,
  useTableState,
} from '../hooks';
import { formatDate } from '../utils/formatDate';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../utils/inventoryRowStatus';

function statusLabel(status: string, t: (key: string) => string): string {
  return status === 'inactive' ? t('clients.status.inactive') : t('clients.status.active');
}

function statusSemantic(status: string): 'success' | 'neutral' {
  return status === 'inactive' ? 'neutral' : 'success';
}

export default function ClientDetail() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const { clientId } = useParams<{ clientId: string }>();
  const safeClientId = (clientId ?? '').trim();
  const [createSupplierOpen, setCreateSupplierOpen] = useState(false);
  const [createInventoryOpen, setCreateInventoryOpen] = useState(false);
  const [labelGeneratorOpen, setLabelGeneratorOpen] = useState(false);

  /** TableDataMode: client-bulk — suppliers list for one client. */
  const {
    page: supplierPage,
    pageSize: supplierPageSize,
    setPage: setSupplierPage,
    setPageSize: setSupplierPageSize,
    sortBy: supplierSortBy,
    sortDir: supplierSortDir,
    setSort: setSupplierSort,
  } = useTableState();

  /** TableDataMode: client-bulk — inventories filtered client-side from bulk fetch (page_size: 200). */
  const {
    page: clientInvPage,
    pageSize: clientInvPageSize,
    setPage: setClientInvPage,
    setPageSize: setClientInvPageSize,
    sortBy: clientInvSortBy,
    sortDir: clientInvSortDir,
    setSort: setClientInvSort,
  } = useTableState();

  const invalidClientId = safeClientId === '';

  const clientQuery = useClient(safeClientId || undefined, { enabled: !invalidClientId });
  const suppliersQuery = useClientSuppliers(safeClientId || undefined, undefined, {
    enabled: !invalidClientId,
  });
  const createSupplierMutation = useCreateClientSupplier(safeClientId);
  const createInventoryMutation = useCreateInventory();

  const inventoriesQuery = useInventoriesList(
    { page: 1, page_size: 200, sort_by: 'updated_at', sort_dir: 'desc' },
    { enabled: Boolean(!invalidClientId && clientQuery.data) }
  );

  const clientInventories = useMemo(
    () =>
      (inventoriesQuery.data?.items ?? []).filter(
        (inv) => (inv.client_id ?? '').trim() === safeClientId
      ),
    [inventoriesQuery.data?.items, safeClientId]
  );

  const inventoryColumns = useMemo<DataTableColumn<InventoryListItem>[]>(
    () => [
      {
        id: 'name',
        label: t('inventory.column_inventory'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (inv) => inv.name,
        cell: (inv) => (
          <Button
            component={RouterLink}
            to={pathToInventory(inv.id)}
            size="small"
            variant="text"
            sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
          >
            {inv.name}
          </Button>
        ),
      },
      {
        id: 'status',
        label: t('inventory.column_status'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (inv) => String(inv.status ?? ''),
        cell: (inv) => (
          <StatusBadge
            label={formatInventoryStatusLabel(String(inv.status))}
            semantic={inventoryStatusToBadgeSemantic(String(inv.status))}
          />
        ),
      },
      {
        id: 'aisles',
        label: t('inventory.column_aisles'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (inv) => inv.aisles_count ?? 0,
        cell: (inv) => inv.aisles_count,
      },
    ],
    [t]
  );

  const sortedClientInventories = useMemo(
    () =>
      !clientInvSortBy.trim()
        ? clientInventories
        : sortDataTableRows(clientInventories, inventoryColumns, clientInvSortBy, clientInvSortDir),
    [clientInventories, inventoryColumns, clientInvSortBy, clientInvSortDir]
  );

  const supplierColumns = useMemo<DataTableColumn<ClientSupplier>[]>(
    () => [
      {
        id: 'name',
        label: t('clients.suppliers.fields.name'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (supplier) => supplier.name.trim().toLowerCase(),
        cell: (supplier) => (
          <Button
            component={RouterLink}
            to={pathToClientSupplier(safeClientId, supplier.id)}
            size="small"
            variant="text"
            sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
          >
            {supplier.name}
          </Button>
        ),
      },
      {
        id: 'status',
        label: t('clients.suppliers.fields.status'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (supplier) => String(supplier.status ?? ''),
        cell: (supplier) => (
          <StatusBadge
            label={statusLabel(String(supplier.status), t)}
            semantic={statusSemantic(String(supplier.status))}
          />
        ),
      },
      {
        id: 'created_at',
        label: t('clients.suppliers.fields.created_at'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (supplier) => supplier.created_at,
        cell: (supplier) => formatDate(supplier.created_at),
      },
      {
        id: 'updated_at',
        label: t('clients.suppliers.fields.updated_at'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (supplier) => supplier.updated_at,
        cell: (supplier) => formatDate(supplier.updated_at),
      },
    ],
    [safeClientId, t]
  );

  const supplierItems = useMemo(() => suppliersQuery.data?.items ?? [], [suppliersQuery.data?.items]);

  const sortedSuppliers = useMemo(
    () =>
      !supplierSortBy.trim()
        ? supplierItems
        : sortDataTableRows(supplierItems, supplierColumns, supplierSortBy, supplierSortDir),
    [supplierItems, supplierColumns, supplierSortBy, supplierSortDir]
  );

  const paginatedSuppliers = useMemo(() => {
    const start = (supplierPage - 1) * supplierPageSize;
    return sortedSuppliers.slice(start, start + supplierPageSize);
  }, [sortedSuppliers, supplierPage, supplierPageSize]);

  const paginatedClientInventories = useMemo(() => {
    const start = (clientInvPage - 1) * clientInvPageSize;
    return sortedClientInventories.slice(start, start + clientInvPageSize);
  }, [sortedClientInventories, clientInvPage, clientInvPageSize]);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: t('clients.breadcrumb_list'), to: ROUTE_CLIENTS }]}
        title={clientQuery.data?.name}
        a11yTitle={t('clients.detail.title')}
        actions={
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
            <Button variant="contained" size="small" onClick={() => setCreateInventoryOpen(true)} disabled={!safeClientId}>
              {t('clients.detail.create_inventory')}
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setLabelGeneratorOpen(true)}
              disabled={!safeClientId || !clientQuery.data}
            >
              {t('clients.labels.action_generate')}
            </Button>
            <Button component={RouterLink} to={ROUTE_CLIENTS} variant="outlined" size="small">
              {t('clients.detail.back_to_list')}
            </Button>
          </Box>
        }
      />

      {invalidClientId ? (
        <ErrorAlert message={t('clients.detail.invalid')} />
      ) : null}

      {!invalidClientId && clientQuery.isLoading ? (
        <LoadingBlock message={t('clients.detail.loading')} py={2} sx={{ mb: 2, justifyContent: 'flex-start' }} />
      ) : null}

      {!invalidClientId && clientQuery.isError ? (
        <ErrorAlert
          error={clientQuery.error}
          message={t('clients.detail.error')}
          onRetry={() => clientQuery.refetch()}
          retryLabel={t('common.retry')}
        />
      ) : null}

      {!invalidClientId && clientQuery.data ? (
        <SectionCard title={t('clients.detail.info_title')}>
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Typography variant="body2">
              <strong>{t('clients.detail.fields.name')}:</strong>{' '}
              {clientQuery.data.name || t('clients.common.no_information')}
            </Typography>
            <Typography variant="body2">
              <strong>{t('clients.detail.fields.status')}:</strong>{' '}
              {statusLabel(String(clientQuery.data.status), t)}
            </Typography>
            <Typography variant="body2">
              <strong>{t('clients.detail.fields.created_at')}:</strong> {formatDate(clientQuery.data.created_at)}
            </Typography>
            <Typography variant="body2">
              <strong>{t('clients.detail.fields.updated_at')}:</strong> {formatDate(clientQuery.data.updated_at)}
            </Typography>
          </Box>
        </SectionCard>
      ) : null}

      {!invalidClientId && clientQuery.data ? (
        <SectionCard
          title={t('clients.suppliers.title')}
          subtitle={t('clients.suppliers.subtitle')}
          actions={
            <Button
              variant="contained"
              onClick={() => setCreateSupplierOpen(true)}
              disabled={!safeClientId}
            >
              {t('clients.suppliers.actions.create')}
            </Button>
          }
        >
          {suppliersQuery.isLoading ? (
            <LoadingBlock message={t('clients.suppliers.loading')} py={2} sx={{ justifyContent: 'flex-start' }} />
          ) : suppliersQuery.isError ? (
            <ErrorAlert
              error={suppliersQuery.error}
              message={t('clients.suppliers.error')}
              onRetry={() => suppliersQuery.refetch()}
              retryLabel={t('common.retry')}
            />
          ) : (suppliersQuery.data?.items ?? []).length === 0 ? (
            <EmptyState
              title={t('clients.suppliers.empty_title')}
              message={t('clients.suppliers.empty_description')}
              action={
                <Button
                  variant="contained"
                  onClick={() => setCreateSupplierOpen(true)}
                  disabled={!safeClientId}
                >
                  {t('clients.suppliers.actions.create')}
                </Button>
              }
            />
          ) : (
            <DataTable<ClientSupplier>
              rows={paginatedSuppliers}
              rowKey={(supplier) => supplier.id}
              columns={supplierColumns}
              loading={false}
              sort={{
                sortBy: supplierSortBy,
                sortDir: supplierSortDir,
                onSortChange: setSupplierSort,
              }}
              pagination={{
                page: supplierPage,
                pageSize: supplierPageSize,
                totalItems: sortedSuppliers.length,
                onPageChange: setSupplierPage,
                onPageSizeChange: setSupplierPageSize,
              }}
            />
          )}
        </SectionCard>
      ) : null}

      {!invalidClientId && clientQuery.data ? (
        <SectionCard
          title={t('clients.detail.inventories_title')}
          subtitle={t('clients.detail.inventories_subtitle')}
          actions={
            <Button variant="outlined" size="small" onClick={() => setCreateInventoryOpen(true)} disabled={!safeClientId}>
              {t('clients.detail.create_inventory')}
            </Button>
          }
        >
          {inventoriesQuery.isLoading ? (
            <LoadingBlock message={t('common.loading')} py={2} sx={{ justifyContent: 'flex-start' }} />
          ) : inventoriesQuery.isError ? (
            <ErrorAlert
              error={inventoriesQuery.error}
              message={t('clients.detail.inventories_error')}
              onRetry={() => inventoriesQuery.refetch()}
              retryLabel={t('common.retry')}
            />
          ) : clientInventories.length === 0 ? (
            <EmptyState
              title={t('clients.detail.inventories_empty')}
              message={t('clients.detail.inventories_empty_hint')}
              action={
                <Button variant="contained" onClick={() => setCreateInventoryOpen(true)} disabled={!safeClientId}>
                  {t('clients.detail.create_inventory')}
                </Button>
              }
            />
          ) : (
            <DataTable<InventoryListItem>
              rows={paginatedClientInventories}
              rowKey={(inv) => inv.id}
              columns={inventoryColumns}
              loading={false}
              sort={{
                sortBy: clientInvSortBy,
                sortDir: clientInvSortDir,
                onSortChange: setClientInvSort,
              }}
              pagination={{
                page: clientInvPage,
                pageSize: clientInvPageSize,
                totalItems: sortedClientInventories.length,
                onPageChange: setClientInvPage,
                onPageSizeChange: setClientInvPageSize,
              }}
            />
          )}
        </SectionCard>
      ) : null}

      <CreateClientSupplierDialog
        open={createSupplierOpen}
        clientId={safeClientId}
        onClose={() => setCreateSupplierOpen(false)}
        onSuccess={() => {
          showSnackbar(t('clients.suppliers.dialogs.create.success'), 'success');
        }}
        onError={(msg) => {
          if (!msg) return;
          showSnackbar(msg, 'error');
        }}
        createClientSupplierFn={createSupplierMutation.mutateAsync}
      />

      <CreateInventoryDialog
        open={createInventoryOpen}
        defaultClientId={safeClientId}
        onClose={() => setCreateInventoryOpen(false)}
        onSuccess={(created) => {
          showSnackbar(t('inventory.created_snackbar', { name: created.name }), 'success');
          navigate(pathToInventory(created.id));
        }}
        onError={(msg) => {
          if (msg) showSnackbar(msg, 'error');
        }}
        createInventoryFn={createInventoryMutation.mutateAsync}
      />

      {clientQuery.data ? (
        <LabelGeneratorDialog
          open={labelGeneratorOpen}
          onClose={() => setLabelGeneratorOpen(false)}
          clientId={safeClientId}
          clientName={clientQuery.data.name}
          suppliers={supplierItems}
          suppliersLoading={suppliersQuery.isLoading}
        />
      ) : null}
    </>
  );
}
