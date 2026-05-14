import type { ChangeEvent, RefObject } from 'react';
import { useMemo, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { Box, Button, Typography } from '@mui/material';
import {
  DataTable,
  FilterToolbar,
  RowActionMenu,
  SectionCard,
  StatusBadge,
  TableSearchField,
  type DataTableColumn,
  type DataTableSortDirection,
  sortDataTableRows,
} from '../../../components/ui';
import { pathToAisleObservability, pathToClientSupplier } from '../../../constants/appRoutes';
import { pathToAislePositions } from '../../../utils/resultRoutes';
import {
  computeProcessAisleMenuState,
  type AisleInventoryTableRow,
  type ProcessAisleMenuContext,
} from '../adapters';

export interface InventoryAislesSectionProps {
  inventoryId: string;
  /** When set, aisle rows can link to supplier detail for `client_supplier_id`. */
  inventoryClientId?: string | null;
  /** All aisles (for empty vs filter-empty). */
  tableRows: AisleInventoryTableRow[];
  filteredTableRows: AisleInventoryTableRow[];
  aislesLoading: boolean;
  aisleTableSearch: string;
  onAisleTableSearch: (v: string) => void;
  onRefreshAisles: () => void;
  fileInputRef: RefObject<HTMLInputElement>;
  onFileInputChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onRequestUpload: (aisleId: string) => void;
  onRequestProcess: (aisleId: string, aisleCode: string, clientSupplierId: string | null) => void;
  aislesDataLoaded: boolean;
  processingAisleId: string | null;
  uploadingAisleId: string | null;
  onOpenCreateAisle: () => void;
}

export default function InventoryAislesSection({
  inventoryId,
  inventoryClientId = null,
  tableRows,
  filteredTableRows,
  aislesLoading,
  aisleTableSearch,
  onAisleTableSearch,
  onRefreshAisles,
  fileInputRef,
  onFileInputChange,
  onRequestUpload,
  onRequestProcess,
  aislesDataLoaded,
  processingAisleId,
  uploadingAisleId,
  onOpenCreateAisle,
}: InventoryAislesSectionProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const emptyLabel = t('common.em_dash');
  const [aisleSortBy, setAisleSortBy] = useState('');
  const [aisleSortDir, setAisleSortDir] = useState<DataTableSortDirection>('asc');

  const handleAisleSortChange = useCallback((sortBy: string, sortDir: DataTableSortDirection) => {
    setAisleSortBy(sortBy);
    setAisleSortDir(sortDir);
  }, []);

  const menuCtx: ProcessAisleMenuContext = useMemo(
    () => ({
      aislesDataLoaded,
      aislesLoading,
      processingAisleId,
    }),
    [aislesDataLoaded, aislesLoading, processingAisleId]
  );

  const columns = useMemo<DataTableColumn<AisleInventoryTableRow>[]>(
    () => [
      {
        id: 'code',
        label: t('aisle.code_label'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => row.presentation.code.toLowerCase(),
        cell: (row) => (
          <Button
            variant="text"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              navigate(pathToAislePositions(inventoryId, row.presentation.id));
            }}
            sx={{
              fontWeight: 650,
              textTransform: 'none',
              px: 0,
              minWidth: 0,
              justifyContent: 'flex-start',
              '&:hover': { textDecoration: 'underline', backgroundColor: 'transparent' },
            }}
          >
            {row.presentation.code}
          </Button>
        ),
      },
      {
        id: 'client_supplier',
        label: t('inventory.column_aisle_supplier'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => (row.presentation.clientSupplierId ?? '').toLowerCase(),
        cell: (row) => {
          const sid = row.presentation.clientSupplierId;
          if (!sid) {
            return (
              <Typography variant="body2" color="text.secondary">
                {t('inventory.aisle_no_supplier')}
              </Typography>
            );
          }
          const cid = (inventoryClientId ?? '').trim();
          if (!cid) {
            return (
              <Typography variant="body2" color="text.secondary">
                {t('inventory.aisle_supplier_assigned_no_nav')}
              </Typography>
            );
          }
          return (
            <Button
              component={RouterLink}
              to={pathToClientSupplier(cid, sid)}
              size="small"
              variant="text"
              onClick={(e) => e.stopPropagation()}
              sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
            >
              {t('inventory.aisle_supplier_view_link')}
            </Button>
          );
        },
      },
      {
        id: 'aisle_status',
        label: t('aisle.column_aisle_status'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => String(row.action.processMenuAisle.status),
        cell: (row) => (
          <StatusBadge
            label={row.presentation.aisleStatusLabel}
            semantic={row.presentation.aisleStatusSemantic}
          />
        ),
      },
      {
        id: 'assets',
        label: t('aisle.column_assets'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (row) => row.presentation.assetsCount,
        cell: (row) => row.presentation.assetsCountDisplay,
      },
      {
        id: 'processing',
        label: t('aisle.column_processing'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => row.presentation.latestRun?.jobStatusRaw ?? '',
        cell: (row) =>
          row.presentation.latestRun ? (
            <StatusBadge
              label={row.presentation.latestRun.statusLabel}
              semantic={row.presentation.latestRun.statusSemantic}
            />
          ) : (
            emptyLabel
          ),
      },
      {
        id: 'run_provider',
        label: t('aisle.column_run_provider'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => row.presentation.latestRun?.providerRaw ?? '',
        cell: (row) => row.presentation.latestRun?.providerDisplay ?? emptyLabel,
      },
      {
        id: 'run_model',
        label: t('aisle.column_run_model'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => row.presentation.latestRun?.modelRaw ?? '',
        cell: (row) => row.presentation.latestRun?.modelDisplay ?? emptyLabel,
      },
      {
        id: 'reference_usage',
        label: t('aisle.column_reference_usage'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (row) => row.presentation.referenceUsage?.label ?? '',
        cell: (row) => {
          const summary = row.presentation.referenceUsage;
          if (!summary) return emptyLabel;
          return (
            <Box sx={{ display: 'grid', gap: 0.5, maxWidth: 180 }}>
              <StatusBadge label={summary.label} semantic={summary.semantic} />
              {summary.detail ? (
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3 }}>
                  {summary.detail}
                </Typography>
              ) : null}
            </Box>
          );
        },
      },
      {
        id: 'results_found',
        label: t('aisle.column_results_found'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (row) => row.presentation.positionsCount,
        cell: (row) => row.presentation.positionsCountDisplay,
      },
      {
        id: 'pending_review',
        label: t('aisle.column_pending_review'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (row) => row.presentation.pendingReviewCount,
        cell: (row) => row.presentation.pendingReviewDisplay,
      },
      {
        id: 'last_updated',
        label: t('common.last_updated'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (row) => row.presentation.lastUpdatedSortKey,
        cell: (row) => row.presentation.lastUpdatedDisplay,
      },
      {
        id: 'actions',
        label: t('common.actions'),
        align: 'right',
        sortable: false,
        width: 56,
        cell: (row) => {
          const processState = computeProcessAisleMenuState(row.action.processMenuAisle, menuCtx);
          const p = row.presentation;
          return (
            <RowActionMenu
              ariaLabel={t('aisle.row_actions_a11y', { code: p.code })}
              items={[
                {
                  id: 'upload_assets',
                  label: uploadingAisleId === p.id ? t('common.uploading') : t('aisle.upload_assets'),
                  onClick: () => onRequestUpload(p.id),
                  disabled: uploadingAisleId === p.id,
                },
                {
                  id: 'execution_logs',
                  label: t('aisle.view_observability'),
                  onClick: () =>
                    navigate(
                      pathToAisleObservability(inventoryId, p.id, row.action.observabilityInitialRunId)
                    ),
                },
                {
                  id: 'process',
                  label: processingAisleId === p.id ? t('common.starting') : t('aisle.process_aisle'),
                  onClick: () => void onRequestProcess(p.id, p.code, p.clientSupplierId ?? null),
                  disabled: processState.disabled,
                  disabledReason:
                    processState.disabledReasonKey !== undefined
                      ? t(processState.disabledReasonKey)
                      : undefined,
                },
              ]}
            />
          );
        },
      },
    ],
    [
      emptyLabel,
      inventoryClientId,
      inventoryId,
      menuCtx,
      navigate,
      onRequestProcess,
      onRequestUpload,
      processingAisleId,
      t,
      uploadingAisleId,
    ]
  );

  const aisleRowsForDisplay = useMemo(
    () =>
      !aisleSortBy.trim()
        ? filteredTableRows
        : sortDataTableRows(filteredTableRows, columns, aisleSortBy, aisleSortDir),
    [filteredTableRows, columns, aisleSortBy, aisleSortDir]
  );

  return (
    <SectionCard
      title={t('aisle.list_title')}
      subtitle={t('aisle.list_subtitle')}
      actions={
        <Button variant="outlined" size="small" onClick={onRefreshAisles} disabled={aislesLoading}>
          {t('common.refresh')}
        </Button>
      }
      variant="elevation"
      elevation={1}
    >
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*,video/*"
        multiple
        style={{ display: 'none' }}
        onChange={onFileInputChange}
      />
      <FilterToolbar
        onReset={() => {
          setAisleSortBy('');
          onAisleTableSearch('');
        }}
        resetDisabled={!aisleTableSearch.trim() && !aisleSortBy.trim()}
      >
        <TableSearchField
          label={t('table.search_label')}
          placeholder={t('aisle.search_aisles_placeholder')}
          value={aisleTableSearch}
          onChange={onAisleTableSearch}
          data-testid="inventory-aisles-search"
        />
      </FilterToolbar>
      <DataTable<AisleInventoryTableRow>
        rows={aisleRowsForDisplay}
        rowKey={(row) => row.presentation.id}
        columns={columns}
        loading={aislesLoading}
        sort={{
          sortBy: aisleSortBy,
          sortDir: aisleSortDir,
          onSortChange: handleAisleSortChange,
        }}
        onRowClick={(row) => navigate(pathToAislePositions(inventoryId, row.presentation.id))}
        emptyState={
          aisleTableSearch.trim() &&
          !aislesLoading &&
          tableRows.length > 0 &&
          filteredTableRows.length === 0
            ? { message: t('table.empty_no_match') }
            : {
                title: t('aisle.empty_table_title'),
                message: t('aisle.empty_table_message'),
                action: (
                  <Button variant="contained" onClick={onOpenCreateAisle}>
                    {t('aisle.create')}
                  </Button>
                ),
              }
        }
      />
    </SectionCard>
  );
}
