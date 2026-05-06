import type { ReactNode } from 'react';
import { Box, Button, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { PageHeader, type PageHeaderBreadcrumb } from '../../../components/shell';

export interface AisleResultsHeaderProps {
  breadcrumbs: PageHeaderBreadcrumb[];
  title: string;
  subtitle: string;
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
}

export default function AisleResultsHeader({
  breadcrumbs,
  title,
  subtitle,
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
}: AisleResultsHeaderProps) {
  const { t } = useTranslation();

  return (
    <PageHeader
      breadcrumbs={breadcrumbs}
      title={title}
      subtitle={subtitle}
      actions={
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
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
          {showCompareRuns ? (
            <Button size="small" variant="outlined" onClick={onCompareRuns}>
              {t('positions.compare_runs')}
            </Button>
          ) : null}
          {showCompareOperational ? (
            <Tooltip title={t('aisle.compare_runs_tooltip')}>
              <Button size="small" variant="outlined" onClick={onCompareOperational}>
                {t('positions.compare_to_operational')}
              </Button>
            </Tooltip>
          ) : null}
          {showPromoteRun ? (
            <Button size="small" variant="outlined" onClick={onPromoteRun}>
              {t('positions.promote_run')}
            </Button>
          ) : null}
          <Button size="small" variant="outlined" disabled={exportDisabled} onClick={onExport}>
            {exportingCsv ? t('common.exporting') : t('positions.export_aisle_csv')}
          </Button>
          <Button size="small" variant="outlined" onClick={onRefresh} disabled={refreshDisabled}>
            {t('common.refresh')}
          </Button>
        </Box>
      }
    />
  );
}
