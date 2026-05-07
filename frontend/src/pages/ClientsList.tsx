import { useMemo, useState } from 'react';
import { Button } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { Client } from '../api/types';
import CreateClientDialog from '../components/CreateClientDialog';
import { PageHeader } from '../components/shell';
import {
  DataTable,
  ErrorAlert,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
  type DataTableColumn,
} from '../components/ui';
import { pathToClient } from '../constants/appRoutes';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import { useClients, useCreateClient } from '../hooks';
import { formatDate } from '../utils/formatDate';

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
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);

  const listQuery = useMemo(
    () => ({ page, page_size: pageSize }),
    [page, pageSize]
  );

  const clientsQuery = useClients(listQuery);
  const clients: Client[] = clientsQuery.data?.items ?? [];

  const columns = useMemo<DataTableColumn<Client>[]>(
    () => [
      {
        id: 'name',
        label: t('clients.fields.name'),
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
        cell: (client) => formatDate(client.created_at),
      },
      {
        id: 'actions',
        label: t('common.actions'),
        cell: (client) => (
          <Button component={RouterLink} to={pathToClient(client.id)} size="small" variant="text">
            {t('clients.actions.view_detail')}
          </Button>
        ),
      },
      {
        id: 'updated_at',
        label: t('clients.fields.updated_at'),
        cell: (client) => formatDate(client.updated_at),
      },
    ],
    [t]
  );

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

      {clientsQuery.isError ? (
        <ErrorAlert
          error={clientsQuery.error}
          message={t('errors.load_clients')}
          onRetry={() => clientsQuery.refetch()}
          retryLabel={t('common.retry')}
        />
      ) : null}

      {!clientsQuery.isError ? (
        <SectionCard title={t('clients.page.title')} subtitle={t('clients.page.subtitle')}>
          <DataTable<Client>
            rows={clients}
            rowKey={(client) => client.id}
            columns={columns}
            loading={clientsQuery.isLoading}
            emptyState={{
              title: t('clients.list.empty_title'),
              message: t('clients.list.empty_description'),
              action: (
                <Button variant="contained" onClick={() => setCreateOpen(true)}>
                  {t('clients.actions.create')}
                </Button>
              ),
            }}
            pagination={
              clientsQuery.data
                ? {
                    page,
                    pageSize,
                    totalItems: clientsQuery.data.total_items,
                    onPageChange: setPage,
                    onPageSizeChange: setPageSize,
                  }
                : undefined
            }
          />
        </SectionCard>
      ) : null}

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
