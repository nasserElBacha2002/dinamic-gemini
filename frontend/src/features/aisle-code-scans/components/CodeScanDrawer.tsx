import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  CircularProgress,
  Drawer,
  Typography,
} from '@mui/material';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import { ConfirmDialog, DrawerHeader, ErrorAlert, LoadingBlock, useAppSnackbar } from '../../../components/ui';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAisleCodeScans, useAisleCodeScanSummary, useRunAisleCodeScan } from '../hooks';
import CodeScanDetectionsTable from './CodeScanDetectionsTable';
import CodeScanEmptyState from './CodeScanEmptyState';
import CodeScanRunSummary from './CodeScanRunSummary';
import CodeScanSummaryTable from './CodeScanSummaryTable';
import CodeScanWarnings from './CodeScanWarnings';

export interface CodeScanDrawerProps {
  open: boolean;
  onClose: () => void;
  inventoryId: string;
  aisleId: string;
  jobIdForPreview?: string | null;
}

export default function CodeScanDrawer({
  open,
  onClose,
  inventoryId,
  aisleId,
  jobIdForPreview,
}: CodeScanDrawerProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [confirmRerunOpen, setConfirmRerunOpen] = useState(false);

  const scansQuery = useAisleCodeScans(inventoryId, aisleId, { enabled: open });
  const summaryQuery = useAisleCodeScanSummary(inventoryId, aisleId, { enabled: open });
  const runMutation = useRunAisleCodeScan(inventoryId, aisleId);

  const latestRun = scansQuery.data?.latest_run ?? summaryQuery.data?.latest_run ?? null;
  const detections = scansQuery.data?.detections ?? [];
  const summaryItems = summaryQuery.data?.items ?? [];

  const isLoading = scansQuery.isLoading || summaryQuery.isLoading;
  const isError = scansQuery.isError || summaryQuery.isError;
  const loadError = scansQuery.error ?? summaryQuery.error;

  const hasRun = Boolean(latestRun);
  const hasDetections = detections.length > 0 || (latestRun?.total_codes_found ?? 0) > 0;

  const runScan = useCallback(async () => {
    try {
      await runMutation.mutateAsync();
      showSnackbar(t('aisleCodeScans.states.scanSuccess'), 'success');
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisleCodeScans.errors.run_failed'), 'error');
    }
  }, [runMutation, showSnackbar, t]);

  const handleRunClick = useCallback(() => {
    if (hasRun) {
      setConfirmRerunOpen(true);
      return;
    }
    void runScan();
  }, [hasRun, runScan]);

  const headerActions = useMemo(() => {
    if (!hasRun) {
      return null;
    }
    return (
      <Button
        size="small"
        variant="contained"
        startIcon={
          runMutation.isPending ? (
            <CircularProgress size={16} color="inherit" aria-hidden />
          ) : (
            <QrCodeScannerIcon fontSize="small" />
          )
        }
        onClick={handleRunClick}
        disabled={runMutation.isPending}
      >
        {t('aisleCodeScans.actions.rerun')}
      </Button>
    );
  }, [handleRunClick, hasRun, runMutation.isPending, t]);

  return (
    <>
      <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 520, md: 640 } } }}>
        <DrawerHeader
          title={
            <Typography variant="h6" component="h2">
              {t('aisleCodeScans.drawer.title')}
            </Typography>
          }
          subtitle={
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {t('aisleCodeScans.drawer.subtitle')}
            </Typography>
          }
          onClose={onClose}
          closeLabel={t('aisleCodeScans.actions.close')}
          actions={headerActions}
        />
        <Box sx={{ px: 2.5, py: 2, overflow: 'auto', flex: 1 }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
            {t('aisleCodeScans.drawer.noMutationNotice')}
          </Typography>

          {isLoading ? <LoadingBlock message={t('aisleCodeScans.states.loading')} /> : null}

          {isError && loadError ? (
            <ErrorAlert message={resolveApiErrorMessage(loadError, 'aisleCodeScans.states.error')} />
          ) : null}

          {!isLoading && !isError && !hasRun ? (
            <CodeScanEmptyState
              variant="no_run"
              onRunScan={() => void runScan()}
              runDisabled={runMutation.isPending}
              runLabel={
                runMutation.isPending
                  ? t('aisleCodeScans.states.scanning')
                  : t('aisleCodeScans.actions.run')
              }
            />
          ) : null}

          {!isLoading && !isError && hasRun && latestRun ? (
            <>
              <CodeScanRunSummary run={latestRun} />
              <CodeScanWarnings warnings={latestRun.warnings ?? []} />
              {!hasDetections ? <CodeScanEmptyState variant="no_detections" /> : null}
              {summaryItems.length > 0 ? <CodeScanSummaryTable items={summaryItems} /> : null}
              {detections.length > 0 ? (
                <CodeScanDetectionsTable
                  detections={detections}
                  inventoryId={inventoryId}
                  aisleId={aisleId}
                  jobIdForPreview={jobIdForPreview}
                />
              ) : null}
            </>
          ) : null}
        </Box>
      </Drawer>

      <ConfirmDialog
        open={confirmRerunOpen}
        title={t('aisleCodeScans.confirmRerun.title')}
        description={t('aisleCodeScans.confirmRerun.body')}
        confirmLabel={t('aisleCodeScans.confirmRerun.confirm')}
        cancelLabel={t('aisleCodeScans.confirmRerun.cancel')}
        onConfirm={() => {
          setConfirmRerunOpen(false);
          void runScan();
        }}
        onClose={() => setConfirmRerunOpen(false)}
        loading={runMutation.isPending}
      />
    </>
  );
}
