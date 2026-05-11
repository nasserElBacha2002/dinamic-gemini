import { useMemo } from 'react';
import type { SyntheticEvent } from 'react';
import { Box, Button, Tab, Tabs, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/types';
import SupplierPromptConfigsModule from '../features/clients/components/SupplierPromptConfigsModule';
import SupplierReferenceImagesModule from '../features/clients/components/SupplierReferenceImagesModule';
import { PageHeader } from '../components/shell';
import { ErrorAlert, LoadingBlock, SectionCard } from '../components/ui';
import { ROUTE_CLIENTS, pathToClient } from '../constants/appRoutes';
import {
  useActiveSupplierPromptConfig,
  useClient,
  useClientSupplier,
  useSupplierReferenceImages,
} from '../hooks';
import { formatDate } from '../utils/formatDate';

const TAB_VALUES = ['resumen', 'prompts', 'imagenes'] as const;
type SupplierDetailTab = (typeof TAB_VALUES)[number];

function normalizeSupplierTab(raw: string | null): SupplierDetailTab {
  const v = (raw ?? '').trim().toLowerCase();
  return v === 'prompts' || v === 'imagenes' ? v : 'resumen';
}

export default function ClientSupplierDetail() {
  const { t } = useTranslation();
  const { clientId, supplierId } = useParams<{ clientId: string; supplierId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = useMemo(() => normalizeSupplierTab(searchParams.get('tab')), [searchParams]);

  const safeClientId = (clientId ?? '').trim();
  const safeSupplierId = (supplierId ?? '').trim();
  const invalid = !safeClientId || !safeSupplierId;

  const clientQuery = useClient(invalid ? undefined : safeClientId, { enabled: !invalid });
  const supplierQuery = useClientSupplier(
    invalid ? undefined : safeClientId,
    invalid ? undefined : safeSupplierId,
    { enabled: !invalid }
  );

  const supplierReady = Boolean(!invalid && supplierQuery.isSuccess && supplierQuery.data);
  const activePromptQuery = useActiveSupplierPromptConfig(
    invalid ? undefined : safeClientId,
    invalid ? undefined : safeSupplierId,
    undefined,
    undefined,
    { enabled: supplierReady }
  );

  const refsQuery = useSupplierReferenceImages(
    invalid ? undefined : safeClientId,
    invalid ? undefined : safeSupplierId,
    { enabled: supplierReady }
  );

  const promptStatusLine = useMemo(() => {
    if (!supplierReady) return t('common.loading');
    if (activePromptQuery.isLoading || activePromptQuery.isFetching) return t('common.loading');
    if (activePromptQuery.data) return t('clients.supplier_page.summary_prompt_active');
    if (activePromptQuery.isError) {
      const err = activePromptQuery.error;
      if (err instanceof ApiError && err.status === 404) {
        return t('clients.supplier_page.summary_prompt_none');
      }
      return t('clients.supplier_page.summary_prompt_error');
    }
    return t('clients.supplier_page.summary_prompt_none');
  }, [
    activePromptQuery.data,
    activePromptQuery.error,
    activePromptQuery.isError,
    activePromptQuery.isFetching,
    activePromptQuery.isLoading,
    supplierReady,
    t,
  ]);

  const refCount = refsQuery.data?.items?.length ?? 0;

  const breadcrumbs = useMemo(() => {
    const clientName = clientQuery.data?.name?.trim() || t('clients.detail.title');
    const supplierName = supplierQuery.data?.name?.trim() || t('clients.supplier_page.title_fallback');
    return [
      { label: t('clients.breadcrumb_list'), to: ROUTE_CLIENTS },
      { label: clientName, to: pathToClient(safeClientId) },
      { label: supplierName },
    ];
  }, [clientQuery.data?.name, supplierQuery.data?.name, safeClientId, t]);

  const handleTabChange = (_: SyntheticEvent, value: unknown) => {
    const nextTab = TAB_VALUES.includes(value as SupplierDetailTab) ? (value as SupplierDetailTab) : 'resumen';
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (nextTab === 'resumen') next.delete('tab');
        else next.set('tab', nextTab);
        return next;
      },
      { replace: true }
    );
  };

  if (invalid) {
    return <ErrorAlert message={t('clients.supplier_page.invalid')} />;
  }

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={supplierQuery.data?.name ?? t('clients.supplier_page.title_fallback')}
        actions={
          <Button component={RouterLink} to={pathToClient(safeClientId)} variant="outlined" size="small">
            {t('clients.supplier_page.back_to_client')}
          </Button>
        }
      />

      {supplierQuery.isLoading ? (
        <LoadingBlock message={t('clients.supplier_page.loading')} py={2} sx={{ mb: 2, justifyContent: 'flex-start' }} />
      ) : null}

      {supplierQuery.isError ? (
        <ErrorAlert
          error={supplierQuery.error}
          message={t('clients.supplier_page.error')}
          onRetry={() => supplierQuery.refetch()}
          retryLabel={t('common.retry')}
        />
      ) : null}

      {supplierQuery.data ? (
        <Box sx={{ width: '100%' }}>
          <Tabs
            value={tab}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
          >
            <Tab value="resumen" label={t('clients.supplier_page.tab_summary')} />
            <Tab value="prompts" label={t('clients.supplier_page.tab_prompts')} />
            <Tab value="imagenes" label={t('clients.supplier_page.tab_reference_images')} />
          </Tabs>

          {tab === 'resumen' ? (
            <SectionCard title={t('clients.supplier_page.config_section_title')}>
              <Box sx={{ display: 'grid', gap: 1.5 }}>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_client')}:</strong>{' '}
                  <Button
                    component={RouterLink}
                    to={pathToClient(safeClientId)}
                    size="small"
                    variant="text"
                    sx={{ minWidth: 0, textTransform: 'none', verticalAlign: 'baseline', p: 0 }}
                  >
                    {clientQuery.data?.name ?? safeClientId}
                  </Button>
                </Typography>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_status')}:</strong>{' '}
                  {String(supplierQuery.data.status) === 'inactive'
                    ? t('clients.status.inactive')
                    : t('clients.status.active')}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_created')}:</strong>{' '}
                  {formatDate(supplierQuery.data.created_at)}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_updated')}:</strong>{' '}
                  {formatDate(supplierQuery.data.updated_at)}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_prompt')}:</strong> {promptStatusLine}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('clients.supplier_page.field_reference_images')}:</strong>{' '}
                  {refsQuery.isLoading
                    ? t('common.loading')
                    : refCount > 0
                      ? t('clients.supplier_page.summary_refs_count', { count: refCount })
                      : t('clients.supplier_page.summary_refs_none')}
                </Typography>
              </Box>
            </SectionCard>
          ) : null}

          {tab === 'prompts' && supplierQuery.data ? (
            <Box sx={{ display: 'grid', gap: 1.5 }} role="tabpanel">
              <Typography variant="subtitle1">{t('clients.supplier_page.prompts_section_title')}</Typography>
              <SupplierPromptConfigsModule
                clientId={safeClientId}
                supplierId={safeSupplierId}
                supplierName={supplierQuery.data.name}
                open
                presentation="inline"
                onClose={() => {}}
              />
            </Box>
          ) : null}

          {tab === 'imagenes' && supplierQuery.data ? (
            <Box sx={{ display: 'grid', gap: 1.5 }} role="tabpanel">
              <Typography variant="subtitle1">{t('clients.supplier_page.reference_section_title')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t('clients.supplier_page.reference_section_intro')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('clients.supplier_page.reference_section_policy')}
              </Typography>
              <SupplierReferenceImagesModule
                clientId={safeClientId}
                supplierId={safeSupplierId}
                supplierName={supplierQuery.data.name}
                open
                presentation="inline"
                onClose={() => {}}
              />
            </Box>
          ) : null}
        </Box>
      ) : null}
    </>
  );
}
