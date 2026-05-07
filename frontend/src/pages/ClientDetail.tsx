import { useMemo } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import type { ClientSupplier } from '../api/types';
import { PageHeader } from '../components/shell';
import {
  DataTable,
  EmptyState,
  ErrorAlert,
  LoadingBlock,
  SectionCard,
  StatusBadge,
  type DataTableColumn,
} from '../components/ui';
import { ROUTE_CLIENTS } from '../constants/appRoutes';
import { useClient, useClientSuppliers } from '../hooks';
import { formatDate } from '../utils/formatDate';

function statusLabel(status: string, t: (key: string) => string): string {
  return status === 'inactive' ? t('clients.status.inactive') : t('clients.status.active');
}

function statusSemantic(status: string): 'success' | 'neutral' {
  return status === 'inactive' ? 'neutral' : 'success';
}

export default function ClientDetail() {
  const { t } = useTranslation();
  const { clientId } = useParams<{ clientId: string }>();
  const safeClientId = (clientId ?? '').trim();

  const invalidClientId = safeClientId === '';

  const clientQuery = useClient(safeClientId || undefined, { enabled: !invalidClientId });
  const suppliersQuery = useClientSuppliers(safeClientId || undefined, undefined, {
    enabled: !invalidClientId,
  });

  const supplierColumns = useMemo<DataTableColumn<ClientSupplier>[]>(
    () => [
      {
        id: 'name',
        label: t('clients.suppliers.fields.name'),
        cell: (supplier) => supplier.name,
      },
      {
        id: 'status',
        label: t('clients.suppliers.fields.status'),
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
        cell: (supplier) => formatDate(supplier.created_at),
      },
      {
        id: 'updated_at',
        label: t('clients.suppliers.fields.updated_at'),
        cell: (supplier) => formatDate(supplier.updated_at),
      },
    ],
    [t]
  );

  return (
    <>
      <PageHeader
        a11yTitle={t('clients.detail.title')}
        actions={
          <Button component={RouterLink} to={ROUTE_CLIENTS} variant="outlined" size="small">
            {t('clients.detail.back_to_list')}
          </Button>
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
              <strong>{t('clients.detail.fields.name')}:</strong> {clientQuery.data.name || t('clients.common.no_information')}
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
            <Button variant="contained" disabled title={t('clients.suppliers.actions.create_disabled_hint')}>
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
                <Button variant="contained" disabled title={t('clients.suppliers.actions.create_disabled_hint')}>
                  {t('clients.suppliers.actions.create')}
                </Button>
              }
            />
          ) : (
            <DataTable<ClientSupplier>
              rows={suppliersQuery.data?.items ?? []}
              rowKey={(supplier) => supplier.id}
              columns={supplierColumns}
              loading={false}
            />
          )}
        </SectionCard>
      ) : null}
    </>
  );
}
