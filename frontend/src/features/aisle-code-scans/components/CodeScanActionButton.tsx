import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@mui/material';
import QrCodeScannerIcon from '@mui/icons-material/QrCodeScanner';
import CodeScanDrawer from './CodeScanDrawer';
import { useRunAisleCodeScan } from '../hooks';

export interface CodeScanActionButtonProps {
  inventoryId: string;
  aisleId: string;
  jobIdForPreview?: string | null;
}

export default function CodeScanActionButton({
  inventoryId,
  aisleId,
  jobIdForPreview,
}: CodeScanActionButtonProps) {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const runMutation = useRunAisleCodeScan(inventoryId, aisleId);

  const handleOpen = useCallback(() => setDrawerOpen(true), []);
  const handleClose = useCallback(() => setDrawerOpen(false), []);

  return (
    <>
      <Button
        data-testid="aisle-code-scan-open"
        size="small"
        variant="outlined"
        startIcon={<QrCodeScannerIcon fontSize="small" />}
        onClick={handleOpen}
        disabled={runMutation.isPending}
        aria-haspopup="dialog"
      >
        {runMutation.isPending ? t('aisleCodeScans.states.scanning') : t('aisleCodeScans.actions.open')}
      </Button>
      <CodeScanDrawer
        open={drawerOpen}
        onClose={handleClose}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobIdForPreview={jobIdForPreview}
      />
    </>
  );
}
