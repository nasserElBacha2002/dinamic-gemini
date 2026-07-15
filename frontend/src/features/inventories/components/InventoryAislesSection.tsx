import type { ChangeEvent, RefObject } from 'react';
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Box, Button, FormControl, InputLabel, MenuItem, Select, Tooltip } from '@mui/material';
import {
  FilterToolbar,
  StatusBadge,
  TableSearchField,
  TableSection,
  type DataTableColumn,
  sortDataTableRows,
} from '../../../components/ui';
import { useTableState } from '../../../hooks';
import { pathToAisleObservability } from '../../../constants/appRoutes';
import { pathToAislePositions } from '../../../utils/resultRoutes';
import { computeProcessAisleMenuState, type AisleInventoryTableRow, type ProcessAisleMenuContext } from '../adapters';

export type AisleActiveFilter = 'active' | 'inactive' | 'all';

export interface InventoryAislesSectionProps {
  inventoryId: string;
  /** All aisles (for empty vs filter-empty). */
  tableRows: AisleInventoryTableRow[];
  filteredTableRows: AisleInventoryTableRow[];
  aislesLoading: boolean;
  aisleTableSearch: string;
  onAisleTableSearch: (v: string) => void;
  aisleActiveFilter?: AisleActiveFilter;
  onAisleActiveFilterChange?: (v: AisleActiveFilter) => void;
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
  tableRows,
  filteredTableRows,
  aislesLoading,
  aisleTableSearch,
  onAisleTableSearch,
  aisleActiveFilter = 'active',
  onAisleActiveFilterChange,
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
  const {
    page,
    pageSize,
    setPage,
    setPageSize,
    sortBy: aisleSortBy,
    sortDir: aisleSortDir,
    setSort: handleAisleSortChange,
  } = useTableState({
    initialSortBy: '',
    initialSortDir: 'asc',
  });

  useEffect(() => {
    setPage(1);
  }, [aisleTableSearch, aisleActiveFilter, setPage]);

  /**
   * TableDataMode: client-bulk — parent fetches aisles in one chunk (`page_size: 200` via `useAislesList`);
   * search and sort run on the loaded rows until server pagination is added.
   */
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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
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
            {!row.presentation.isActive ? (
              <span data-testid={`aisle-inactive-badge-${row.presentation.id}`}>
                <StatusBadge label={t('aisle.inactive_badge')} semantic="neutral" />
              </span>
            ) : null}
          </Box>
        ),
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
        id: 'last_updated',
        label: t('common.last_updated'),
        sortable: true,
        sortType: 'date',
        sortAccessor: (row) => row.presentation.lastUpdatedSortKey,
        cell: (row) => row.presentation.lastUpdatedDisplay,
      },
      {
        id: 'action_upload',
        label: t('aisle.column_action_upload'),
        align: 'center',
        sortable: false,
        width: 112,
        cell: (row) => {
          const p = row.presentation;
          const inactive = !p.isActive;
          const disabled = Boolean(uploadingAisleId) || inactive;
          const btn = (
            <Button
              variant="outlined"
              size="small"
              data-testid={`aisle-action-upload-${p.id}`}
              aria-label={t('aisle.upload_assets_row_a11y', { code: p.code })}
              onClick={(e) => {
                e.stopPropagation();
                onRequestUpload(p.id);
              }}
              disabled={disabled}
            >
              {uploadingAisleId === p.id ? t('uploads.photos.uploadingButton') : t('aisle.upload_assets')}
            </Button>
          );
          if (inactive) {
            return (
              <Tooltip title={t('aisle.operations_disabled_inactive')}>
                <span>{btn}</span>
              </Tooltip>
            );
          }
          return btn;
        },
      },
      {
        id: 'action_observability',
        label: t('aisle.column_action_observability'),
        align: 'center',
        sortable: false,
        width: 112,
        cell: (row) => {
          const p = row.presentation;
          return (
            <Button
              variant="outlined"
              size="small"
              data-testid={`aisle-action-observability-${p.id}`}
              aria-label={t('aisle.observability_row_a11y', { code: p.code })}
              onClick={(e) => {
                e.stopPropagation();
                navigate(pathToAisleObservability(inventoryId, p.id, row.action.observabilityInitialRunId));
              }}
            >
              {t('aisle.action_observability_view')}
            </Button>
          );
        },
      },
      {
        id: 'action_process',
        label: t('aisle.column_action_process'),
        align: 'center',
        sortable: false,
        width: 104,
        cell: (row) => {
          const processState = computeProcessAisleMenuState(row.action.processMenuAisle, menuCtx);
          const p = row.presentation;
          const inactive = !p.isActive;
          const disabled = processState.disabled || inactive;
          const label = processingAisleId === p.id ? t('common.starting') : t('aisle.process_start');
          const btn = (
            <Button
              variant="outlined"
              size="small"
              data-testid={`aisle-action-process-${p.id}`}
              aria-label={t('aisle.process_row_a11y', { code: p.code })}
              disabled={disabled}
              onClick={(e) => {
                e.stopPropagation();
                void onRequestProcess(p.id, p.code, p.clientSupplierId ?? null);
              }}
            >
              {label}
            </Button>
          );
          const reasonKey = inactive
            ? 'aisle.operations_disabled_inactive'
            : processState.disabled && processState.disabledReasonKey
              ? processState.disabledReasonKey
              : null;
          if (disabled && reasonKey) {
            return (
              <Tooltip title={t(reasonKey)}>
                <span>{btn}</span>
              </Tooltip>
            );
          }
          return btn;
        },
      },
    ],
    [
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

  const paginatedAisleRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return aisleRowsForDisplay.slice(start, start + pageSize);
  }, [aisleRowsForDisplay, page, pageSize]);

  const hasActiveFilter = aisleActiveFilter !== 'active';
  const filtersDirty = Boolean(aisleTableSearch.trim()) || Boolean(aisleSortBy.trim()) || hasActiveFilter;

  return (
    <TableSection<AisleInventoryTableRow>
      testId="inventory-aisles-section"
      title={t('aisle.list_title')}
      description={t('aisle.list_subtitle')}
      variant="elevation"
      elevation={1}
      headerActions={
        <Button variant="outlined" size="small" onClick={onRefreshAisles} disabled={aislesLoading}>
          {t('common.refresh')}
        </Button>
      }
      headerSlot={
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*,video/*"
          multiple
          style={{ display: 'none' }}
          onChange={onFileInputChange}
        />
      }
      toolbar={
        <FilterToolbar
          onReset={() => {
            handleAisleSortChange('', 'asc');
            onAisleTableSearch('');
            onAisleActiveFilterChange?.('active');
            setPage(1);
          }}
          resetDisabled={!filtersDirty}
        >
          <TableSearchField
            label={t('table.search_label')}
            placeholder={t('aisle.search_aisles_placeholder')}
            value={aisleTableSearch}
            onChange={onAisleTableSearch}
            data-testid="inventory-aisles-search"
          />
          {onAisleActiveFilterChange ? (
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="aisle-active-filter-label">{t('aisle.filter_active_label')}</InputLabel>
              <Select
                labelId="aisle-active-filter-label"
                label={t('aisle.filter_active_label')}
                value={aisleActiveFilter}
                onChange={(e) => onAisleActiveFilterChange(e.target.value as AisleActiveFilter)}
                data-testid="inventory-aisles-active-filter"
              >
                <MenuItem value="active">{t('aisle.filter_active_only')}</MenuItem>
                <MenuItem value="inactive">{t('aisle.filter_inactive_only')}</MenuItem>
                <MenuItem value="all">{t('aisle.filter_active_all')}</MenuItem>
              </Select>
            </FormControl>
          ) : null}
        </FilterToolbar>
      }
      table={{
        rows: paginatedAisleRows,
        rowKey: (row) => row.presentation.id,
        columns,
        loading: aislesLoading,
        sort: {
          sortBy: aisleSortBy,
          sortDir: aisleSortDir,
          onSortChange: handleAisleSortChange,
        },
        pagination: {
          page,
          pageSize,
          totalItems: aisleRowsForDisplay.length,
          onPageChange: setPage,
          onPageSizeChange: setPageSize,
        },
        onRowClick: (row) => navigate(pathToAislePositions(inventoryId, row.presentation.id)),
        emptyState:
          (aisleTableSearch.trim() || aisleActiveFilter !== 'all') &&
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
              },
      }}
    />
  );
}
