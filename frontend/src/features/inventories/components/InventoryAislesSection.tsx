import type { ChangeEvent, RefObject } from 'react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Box, Button, Typography } from '@mui/material';
import {
  DataTable,
  FilterToolbar,
  RowActionMenu,
  SectionCard,
  StatusBadge,
  TableSearchField,
  type DataTableColumn,
} from '../../../components/ui';
import { pathToAislePositions } from '../../../utils/resultRoutes';
import {
  computeProcessAisleMenuState,
  type AisleInventoryTableRow,
  type ProcessAisleMenuContext,
} from '../adapters';

export interface InventoryAislesSectionProps {
  inventoryId: string;
  /** All aisles (for empty vs filter-empty). */
  tableRows: AisleInventoryTableRow[];
  filteredTableRows: AisleInventoryTableRow[];
  aislesLoading: boolean;
  aisleTableSearch: string;
  onAisleTableSearch: (v: string) => void;
  onRefreshAisles: () => void;
  fileInputRef: RefObject<HTMLInputElement>;
  onFileInputChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onOpenObservability: (p: {
    aisleId: string;
    aisleCode: string;
    initialSelectedRunId: string | null;
  }) => void;
  onRequestUpload: (aisleId: string) => void;
  onRequestProcess: (aisleId: string, aisleCode: string) => void;
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
  onRefreshAisles,
  fileInputRef,
  onFileInputChange,
  onOpenObservability,
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
        id: 'aisle_status',
        label: t('aisle.column_aisle_status'),
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
        cell: (row) => row.presentation.assetsCountDisplay,
      },
      {
        id: 'processing',
        label: t('aisle.column_processing'),
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
        cell: (row) => row.presentation.latestRun?.providerDisplay ?? emptyLabel,
      },
      {
        id: 'run_model',
        label: t('aisle.column_run_model'),
        cell: (row) => row.presentation.latestRun?.modelDisplay ?? emptyLabel,
      },
      {
        id: 'reference_usage',
        label: t('aisle.column_reference_usage'),
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
        cell: (row) => row.presentation.positionsCountDisplay,
      },
      {
        id: 'pending_review',
        label: t('aisle.column_pending_review'),
        align: 'right',
        cell: (row) => row.presentation.pendingReviewDisplay,
      },
      {
        id: 'last_updated',
        label: t('common.last_updated'),
        cell: (row) => row.presentation.lastUpdatedDisplay,
      },
      {
        id: 'actions',
        label: t('common.actions'),
        align: 'right',
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
                  label: t('aisle.view_logs'),
                  onClick: () =>
                    onOpenObservability({
                      aisleId: p.id,
                      aisleCode: p.code,
                      initialSelectedRunId: row.action.observabilityInitialRunId,
                    }),
                },
                {
                  id: 'process',
                  label: processingAisleId === p.id ? t('common.starting') : t('aisle.process_aisle'),
                  onClick: () => void onRequestProcess(p.id, p.code),
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
      inventoryId,
      menuCtx,
      navigate,
      onOpenObservability,
      onRequestProcess,
      onRequestUpload,
      processingAisleId,
      t,
      uploadingAisleId,
    ]
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
      <FilterToolbar onReset={() => onAisleTableSearch('')} resetDisabled={!aisleTableSearch.trim()}>
        <TableSearchField
          label={t('table.search_label')}
          placeholder={t('aisle.search_aisles_placeholder')}
          value={aisleTableSearch}
          onChange={onAisleTableSearch}
          data-testid="inventory-aisles-search"
        />
      </FilterToolbar>
      <DataTable<AisleInventoryTableRow>
        rows={filteredTableRows}
        rowKey={(row) => row.presentation.id}
        columns={columns}
        loading={aislesLoading}
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
