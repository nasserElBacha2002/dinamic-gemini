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
  type AisleInventoryRowViewModel,
  type ProcessAisleMenuContext,
} from '../adapters';

export interface InventoryAislesSectionProps {
  inventoryId: string;
  /** All aisles (for empty vs filter-empty). */
  rowViewModels: AisleInventoryRowViewModel[];
  filteredRowViewModels: AisleInventoryRowViewModel[];
  aislesLoading: boolean;
  aisleTableSearch: string;
  onAisleTableSearch: (v: string) => void;
  onRefreshAisles: () => void;
  fileInputRef: RefObject<HTMLInputElement>;
  onFileInputChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onOpenObservability: (p: {
    aisleId: string;
    aisleCode: string;
    initialSelectedJobId: string | null;
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
  rowViewModels,
  filteredRowViewModels,
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
      t,
    }),
    [aislesDataLoaded, aislesLoading, processingAisleId, t]
  );

  const columns = useMemo<DataTableColumn<AisleInventoryRowViewModel>[]>(
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
              navigate(pathToAislePositions(inventoryId, row.id));
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
            {row.code}
          </Button>
        ),
      },
      {
        id: 'aisle_status',
        label: t('aisle.column_aisle_status'),
        cell: (row) => (
          <StatusBadge label={row.aisleStatusLabel} semantic={row.aisleStatusSemantic} />
        ),
      },
      {
        id: 'assets',
        label: t('aisle.column_assets'),
        align: 'right',
        cell: (row) => row.assetsCountDisplay,
      },
      {
        id: 'processing',
        label: t('aisle.column_processing'),
        cell: (row) =>
          row.execution ? (
            <StatusBadge
              label={row.execution.jobStatusLabel}
              semantic={row.execution.jobStatusSemantic}
            />
          ) : (
            emptyLabel
          ),
      },
      {
        id: 'run_provider',
        label: t('aisle.column_run_provider'),
        cell: (row) => row.execution?.providerDisplay ?? emptyLabel,
      },
      {
        id: 'run_model',
        label: t('aisle.column_run_model'),
        cell: (row) => row.execution?.modelDisplay ?? emptyLabel,
      },
      {
        id: 'reference_usage',
        label: t('aisle.column_reference_usage'),
        cell: (row) => {
          const summary = row.referenceUsage;
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
        cell: (row) => row.positionsCountDisplay,
      },
      {
        id: 'pending_review',
        label: t('aisle.column_pending_review'),
        align: 'right',
        cell: (row) => row.pendingReviewDisplay,
      },
      {
        id: 'last_updated',
        label: t('common.last_updated'),
        cell: (row) => row.lastUpdatedDisplay,
      },
      {
        id: 'actions',
        label: t('common.actions'),
        align: 'right',
        width: 56,
        cell: (row) => {
          const processState = computeProcessAisleMenuState(row.processMenuAisle, menuCtx);
          return (
            <RowActionMenu
              ariaLabel={t('aisle.row_actions_a11y', { code: row.code })}
              items={[
                {
                  id: 'upload_assets',
                  label: uploadingAisleId === row.id ? t('common.uploading') : t('aisle.upload_assets'),
                  onClick: () => onRequestUpload(row.id),
                  disabled: uploadingAisleId === row.id,
                },
                {
                  id: 'execution_logs',
                  label: t('aisle.view_logs'),
                  onClick: () =>
                    onOpenObservability({
                      aisleId: row.id,
                      aisleCode: row.code,
                      initialSelectedJobId: row.executionJobId,
                    }),
                },
                {
                  id: 'process',
                  label: processingAisleId === row.id ? t('common.starting') : t('aisle.process_aisle'),
                  onClick: () => void onRequestProcess(row.id, row.code),
                  disabled: processState.disabled,
                  disabledReason: processState.disabledReason,
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
      <DataTable<AisleInventoryRowViewModel>
        rows={filteredRowViewModels}
        rowKey={(row) => row.id}
        columns={columns}
        loading={aislesLoading}
        onRowClick={(row) => navigate(pathToAislePositions(inventoryId, row.id))}
        emptyState={
          aisleTableSearch.trim() &&
          !aislesLoading &&
          rowViewModels.length > 0 &&
          filteredRowViewModels.length === 0
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
