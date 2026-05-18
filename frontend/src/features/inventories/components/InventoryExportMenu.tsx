import { useState, type MouseEvent } from 'react';
import { Button, Menu, MenuItem } from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import { useTranslation } from 'react-i18next';
import {
  exportInventoryPackageZip,
  exportInventorySummaryCsv,
} from '../../../api/client';
import { ApiError } from '../../../api/types';
import { useAppSnackbar } from '../../../components/ui';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';

export interface InventoryExportMenuProps {
  inventoryId: string;
  disabled?: boolean;
}

export default function InventoryExportMenu({ inventoryId, disabled }: InventoryExportMenuProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [exporting, setExporting] = useState<'summary' | 'package' | null>(null);
  const open = Boolean(anchorEl);

  const handleOpen = (event: MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const runExport = async (kind: 'summary' | 'package') => {
    if (!inventoryId) return;
    setExporting(kind);
    try {
      if (kind === 'summary') {
        await exportInventorySummaryCsv(inventoryId);
      } else {
        await exportInventoryPackageZip(inventoryId);
      }
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
    } finally {
      setExporting(null);
      handleClose();
    }
  };

  return (
    <>
      <Button
        data-testid="inventory-export-menu"
        variant="outlined"
        size="small"
        disabled={disabled || !inventoryId || exporting !== null}
        endIcon={<KeyboardArrowDownIcon fontSize="small" />}
        onClick={handleOpen}
        aria-controls={open ? 'inventory-export-menu-list' : undefined}
        aria-haspopup="menu"
        aria-expanded={open ? 'true' : undefined}
      >
        {exporting ? t('common.exporting') : t('inventory.export_menu')}
      </Button>
      <Menu
        id="inventory-export-menu-list"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <MenuItem
          data-testid="inventory-export-summary"
          disabled={exporting !== null}
          onClick={() => void runExport('summary')}
        >
          {t('inventory.export_summary')}
        </MenuItem>
        <MenuItem
          data-testid="inventory-export-package"
          disabled={exporting !== null}
          onClick={() => void runExport('package')}
        >
          {t('inventory.export_package_zip')}
        </MenuItem>
      </Menu>
    </>
  );
}
