import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Menu, MenuItem } from '@mui/material';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { exportAisleCodeScansCsv } from '../../../api/codeScansApi';
import type { CodeScanExportType } from '../../../api/types/codeScans';
import { useAppSnackbar } from '../../../components/ui';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';

export interface CodeScanExportMenuProps {
  inventoryId: string;
  aisleId: string;
  disabled?: boolean;
}

export default function CodeScanExportMenu({
  inventoryId,
  aisleId,
  disabled,
}: CodeScanExportMenuProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
  const [exporting, setExporting] = useState(false);

  const handleExport = async (exportType: CodeScanExportType) => {
    setAnchor(null);
    setExporting(true);
    try {
      await exportAisleCodeScansCsv(inventoryId, aisleId, exportType);
      showSnackbar(t('aisleCodeScans.exports.success'), 'success');
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisleCodeScans.exports.error'), 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={<FileDownloadOutlinedIcon fontSize="small" />}
        onClick={(e) => setAnchor(e.currentTarget)}
        disabled={disabled || exporting}
        data-testid="code-scan-export-button"
      >
        {t('aisleCodeScans.exports.button')}
      </Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => void handleExport('detections')}>
          {t('aisleCodeScans.exports.detections')}
        </MenuItem>
        <MenuItem onClick={() => void handleExport('unmatched')}>
          {t('aisleCodeScans.exports.unmatched')}
        </MenuItem>
        <MenuItem onClick={() => void handleExport('summary')}>
          {t('aisleCodeScans.exports.summary')}
        </MenuItem>
      </Menu>
    </>
  );
}
