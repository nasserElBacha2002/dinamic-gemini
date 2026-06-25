import { useEffect, useMemo, useState } from 'react';
import { Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { Client } from '../api/types';
import CreateClientDialog from '../components/CreateClientDialog';
import { PageHeader } from '../components/shell';
import {
  FilterToolbar,
  StatusBadge,
  TableSearchField,
  TableSection,
  sortDataTableRows,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { pathToClient } from '../constants/appRoutes';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { useClients, useCreateClient, useTableState } from '../hooks';
import { formatDate } from '../utils/formatDate';
import { rowMatchesSearchQuery } from '../utils/tableSearch';

function clientStatusLabel(status: string, t: (key: string) => string): string {
  return status === 'inactive' ? t('clients.status.inactive') : t('clients.status.active');
}

function clientStatusSemantic(status: string): 'success' | 'neutral' {
  return status === 'inactive' ? 'neutral' : 'success';
}

export default function ClientsList() {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const createClientMutation = useCreateClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [clientSearch, setClientSearch] = useState('');
  const {
    page,
    pageSize,
    sortBy: clientListSortBy,
    sortDir: clientListSortDir,
    setPage,
    setPageSize,
    setSortWithoutPageReset,
  } = useTableState({
    initialPage: 1,
    initialPageSize: DEFAULT_LIST_PAGE_SIZE,
    initialSortBy: '',
    initialSortDir: 'asc',
  });

  /**
   * TableDataMode: hybrid — server `page` / `page_size` from the API; search and column sort
   * apply only to rows on the current page. Pagination is hidden while search is active.
   */
  const listQuery = useMemo(
    () => ({ page, page_size: pageSize }),
    [page, pageSize]
  );

  const clientsQuery = useClients(listQuery);
  const clientItems = useMemo(() => clientsQuery.data?.items ?? [], [clientsQuery.data?.items]);

  useEffect(() => {
    setPage(1);
  }, [clientSearch, setPage]);

  const displayedClients = useMemo(
    () => clientItems.filter((c) => rowMatchesSearchQuery(clientSearch, [c.name, c.id])),
    [clientItems, clientSearch]
  );

  const columns = useMemo<DataTableColumn<Client>[]>(
    () => [
      {
        id: 'name',
        label: t('clients.fields.name'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (client) => client.name.trim().toLowerCase(),
        cell: (client) => (
          <Button
            component={RouterLink}
            to={pathToClient(client.id)}
            size="small"
            variant="text"
            sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
          >
            {client.name}
          </Button>
        ),
      },
      {
        id: 'status',
        label: t('clients.fields.status'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (client) => String(client.status ?? ''),
        cell: (client) => (
          <StatusBadge
            label={clientStatusLabel(String(client.status), t)}
            semantic={clientStatusSemantic(String(client.status))}
          />
        ),
      },
      {
        id: 'created_at',
        label: t('clients.fields.created_at'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (client) => client.created_at,
        cell: (client) => formatDate(client.created_at),
      },
      {
        id: 'actions',
        label: t('common.actions'),
        sortable: false,
        cell: (client) => (
          <Button component={RouterLink} to={pathToClient(client.id)} size="small" variant="text">
            {t('clients.actions.view_detail')}
          </Button>
        ),
      },
      {
        id: 'updated_at',
        label: t('clients.fields.updated_at'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (client) => client.updated_at,
        cell: (client) => formatDate(client.updated_at),
      },
    ],
    [t]
  );

  const clientsRowsSorted = useMemo(
    () =>
      !clientListSortBy.trim()
        ? displayedClients
        : sortDataTableRows(displayedClients, columns, clientListSortBy, clientListSortDir),
    [displayedClients, columns, clientListSortBy, clientListSortDir]
  );

  const listErrorProps = clientsQuery.isError
    ? {
        error: clientsQuery.error,
        message: t('errors.load_clients'),
        onRetry: () => clientsQuery.refetch(),
        retryLabel: t('common.retry'),
      }
    : null;

  return (
    <>
      <PageHeader
        a11yTitle={t('clients.page.a11y')}
        actions={
          <Button variant="contained" onClick={() => setCreateOpen(true)}>
            {t('clients.actions.create')}
          </Button>
        }
      />

      <TableSection<Client>
        testId="clients-list-section"
        title={t('clients.page.title')}
        description={t('clients.page.subtitle')}
        error={listErrorProps}
        hideSectionOnError
        toolbar={
          <>
            <FilterToolbar
              onReset={() => {
                setClientSearch('');
                setSortWithoutPageReset('', 'asc');
              }}
              resetDisabled={!clientSearch.trim() && !clientListSortBy.trim()}
            >
              <TableSearchField
                label={t('clients.list.search_placeholder')}
                placeholder={t('clients.list.search_placeholder')}
                value={clientSearch}
                onChange={setClientSearch}
                data-testid="clients-list-search"
              />
            </FilterToolbar>
            {clientSearch.trim() ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                {t('clients.list.search_hint_page')}
              </Typography>
            ) : null}
          </>
        }
        table={{
          rows: clientsRowsSorted,
          rowKey: (client) => client.id,
          columns,
          loading: clientsQuery.isLoading,
          sort: {
            sortBy: clientListSortBy,
            sortDir: clientListSortDir,
            onSortChange: setSortWithoutPageReset,
          },
          emptyState:
            clientSearch.trim() && clientItems.length > 0 && displayedClients.length === 0
              ? {
                  title: t('clients.list.search_no_results_title'),
                  message: t('table.empty_no_match'),
                }
              : {
                  title: t('clients.list.empty_title'),
                  message: t('clients.list.empty_description'),
                  action: (
                    <Button variant="contained" onClick={() => setCreateOpen(true)}>
                      {t('clients.actions.create')}
                    </Button>
                  ),
                },
          pagination:
            clientSearch.trim()
              ? undefined
              : clientsQuery.data
                ? {
                    page,
                    pageSize,
                    totalItems: clientsQuery.data.total_items,
                    onPageChange: setPage,
                    onPageSizeChange: setPageSize,
                  }
                : undefined,
        }}
      />

      <CreateClientDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => {
          showSnackbar(t('clients.dialogs.create.success'), 'success');
        }}
        onError={(msg) => {
          if (!msg) return;
          showSnackbar(msg, 'error');
        }}
        createClientFn={createClientMutation.mutateAsync}
      />
    </>
  );
}
