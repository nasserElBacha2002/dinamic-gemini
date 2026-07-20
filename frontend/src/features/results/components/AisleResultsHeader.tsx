import { useState, type MouseEvent, type ReactNode } from 'react';
import { Box, Button, Menu, MenuItem, Tooltip } from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import { useTranslation } from 'react-i18next';
import { PageHeader, type PageHeaderBreadcrumb } from '../../../components/shell';
import { StatusBadge } from '../../../components/ui';

export interface AisleResultsHeaderProps {
  breadcrumbs: PageHeaderBreadcrumb[];
  title: string;
  subtitle: ReactNode;
  /** When false, show inactive badge next to title area via subtitle composition — or pass showInactiveBadge. */
  showInactiveBadge?: boolean;
  assetsAction?: ReactNode;
  mergeButtonVisible: boolean;
  mergeDisabledReason: string;
  mergeButtonDisabled: boolean;
  isMerging: boolean;
  onRunMerge: () => void;
  showCompareRuns: boolean;
  onCompareRuns: () => void;
  showCompareOperational: boolean;
  onCompareOperational: () => void;
  showPromoteRun: boolean;
  onPromoteRun: () => void;
  exportDisabled: boolean;
  exportingCsv: boolean;
  onExport: () => void;
  refreshDisabled: boolean;
  onRefresh: () => void;
  onOpenObservability?: () => void;
  onEditName?: () => void;
  onDeactivate?: () => void;
  onReactivate?: () => void;
}

export default function AisleResultsHeader({
  breadcrumbs,
  title,
  subtitle,
  showInactiveBadge = false,
  assetsAction,
  mergeButtonVisible,
  mergeDisabledReason,
  mergeButtonDisabled,
  isMerging,
  onRunMerge,
  showCompareRuns,
  onCompareRuns,
  showCompareOperational,
  onCompareOperational,
  showPromoteRun,
  onPromoteRun,
  exportDisabled,
  exportingCsv,
  onExport,
  refreshDisabled,
  onRefresh,
  onOpenObservability,
  onEditName,
  onDeactivate,
  onReactivate,
}: AisleResultsHeaderProps) {
  const { t } = useTranslation();
  const [moreActionsAnchorEl, setMoreActionsAnchorEl] = useState<null | HTMLElement>(null);
  const moreActionsOpen = Boolean(moreActionsAnchorEl);

  const handleOpenMoreActions = (event: MouseEvent<HTMLButtonElement>) => {
    setMoreActionsAnchorEl(event.currentTarget);
  };

  const handleCloseMoreActions = () => {
    setMoreActionsAnchorEl(null);
  };

  const titleNode = (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <span>{title}</span>
      {showInactiveBadge ? (
        <span data-testid="aisle-inactive-badge">
          <StatusBadge label={t('aisle.inactive_badge')} semantic="neutral" />
        </span>
      ) : null}
    </Box>
  );

  return (
    <PageHeader
      breadcrumbs={breadcrumbs}
      title={titleNode}
      subtitle={subtitle}
      actions={
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
            flexWrap: 'wrap',
            width: '100%',
          }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flexWrap: 'wrap',
            }}
          >
            {assetsAction ?? null}
            {mergeButtonVisible ? (
              <Tooltip title={mergeDisabledReason} disableHoverListener={!mergeDisabledReason}>
                <span>
                  <Button size="small" variant="contained" onClick={onRunMerge} disabled={mergeButtonDisabled}>
                    {isMerging ? t('common.merging') : t('aisle.merge_repeated_labels')}
                  </Button>
                </span>
              </Tooltip>
            ) : null}
            <>
              <Button
                data-testid="aisle-results-more-actions"
                size="small"
                variant="outlined"
                endIcon={<KeyboardArrowDownIcon fontSize="small" />}
                onClick={handleOpenMoreActions}
                aria-controls={moreActionsOpen ? 'aisle-results-more-actions-menu' : undefined}
                aria-haspopup="menu"
                aria-expanded={moreActionsOpen ? 'true' : undefined}
              >
                {t('positions.more_actions')}
              </Button>
              <Menu
                id="aisle-results-more-actions-menu"
                anchorEl={moreActionsAnchorEl}
                open={moreActionsOpen}
                onClose={handleCloseMoreActions}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
              >
                {onEditName ? (
                  <MenuItem
                    data-testid="aisle-edit-name"
                    onClick={() => {
                      handleCloseMoreActions();
                      onEditName();
                    }}
                  >
                    {t('aisle.edit_name')}
                  </MenuItem>
                ) : null}
                {onDeactivate ? (
                  <MenuItem
                    data-testid="aisle-deactivate"
                    onClick={() => {
                      handleCloseMoreActions();
                      onDeactivate();
                    }}
                  >
                    {t('aisle.deactivate')}
                  </MenuItem>
                ) : null}
                {onReactivate ? (
                  <MenuItem
                    data-testid="aisle-reactivate"
                    onClick={() => {
                      handleCloseMoreActions();
                      onReactivate();
                    }}
                  >
                    {t('aisle.reactivate')}
                  </MenuItem>
                ) : null}
                {showCompareRuns ? (
                  <MenuItem
                    onClick={() => {
                      handleCloseMoreActions();
                      onCompareRuns();
                    }}
                  >
                    {t('positions.compare_runs')}
                  </MenuItem>
                ) : null}
                {showCompareOperational ? (
                  <MenuItem
                    onClick={() => {
                      handleCloseMoreActions();
                      onCompareOperational();
                    }}
                    title={t('aisle.compare_runs_tooltip')}
                  >
                    {t('positions.compare_to_operational')}
                  </MenuItem>
                ) : null}
                {showPromoteRun ? (
                  <MenuItem
                    onClick={() => {
                      handleCloseMoreActions();
                      onPromoteRun();
                    }}
                  >
                    {t('positions.promote_run')}
                  </MenuItem>
                ) : null}
                {onOpenObservability ? (
                  <MenuItem
                    data-testid="aisle-observability-menu-open"
                    onClick={() => {
                      handleCloseMoreActions();
                      onOpenObservability();
                    }}
                  >
                    {t('aisle.view_observability')}
                  </MenuItem>
                ) : null}
                <MenuItem
                  data-testid="aisle-export-operational"
                  onClick={() => {
                    handleCloseMoreActions();
                    void onExport();
                  }}
                  disabled={exportDisabled}
                >
                  {exportingCsv ? t('common.exporting') : t('positions.export_aisle_operational')}
                </MenuItem>
              </Menu>
            </>
          </Box>
          <Button size="small" variant="outlined" onClick={onRefresh} disabled={refreshDisabled}>
            {t('common.refresh')}
          </Button>
        </Box>
      }
    />
  );
}
