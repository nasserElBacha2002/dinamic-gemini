/**
 * RowActionMenu — Re diseño 3.3 §8.7, §15.6: row actions without crowding tables with buttons.
 */

import { useId, useState, type MouseEvent, type ReactNode } from 'react';
import { Box, IconButton, ListItemIcon, ListItemText, Menu, MenuItem } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { TOUCH_TARGET_MIN_PX } from '../shell/layoutConstants';

export interface RowActionMenuItem {
  id: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  /** Shown under the label when disabled (e.g. why the action is unavailable). */
  disabledReason?: string;
  /** Destructive row action — uses error tone (§6.3). */
  danger?: boolean;
  /** Optional leading icon. */
  icon?: ReactNode;
}

export interface RowActionMenuProps {
  items: readonly RowActionMenuItem[];
  /** Accessible label for the trigger (e.g. "Actions for row SKU-123"). */
  ariaLabel: string;
  /** Optional icon button size. */
  size?: 'small' | 'medium' | 'large';
}

export default function RowActionMenu({ items, ariaLabel, size = 'medium' }: RowActionMenuProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);
  const menuId = useId();

  if (items.length === 0) {
    return null;
  }

  const handleOpen = (e: MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    setAnchor(e.currentTarget);
  };
  const handleClose = () => setAnchor(null);

  return (
    <Box
      component="span"
      data-datatable-skip-row-click
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      sx={{ display: 'inline-flex', verticalAlign: 'middle' }}
    >
      <IconButton
        size={size}
        aria-label={ariaLabel}
        aria-controls={open ? menuId : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleOpen}
        sx={{ minWidth: TOUCH_TARGET_MIN_PX, minHeight: TOUCH_TARGET_MIN_PX }}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={open}
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{ sx: { minWidth: 180 } }}
      >
        {items.map((item) => (
          <MenuItem
            key={item.id}
            disabled={item.disabled}
            onClick={(e) => {
              e.stopPropagation();
              handleClose();
              // Defer so the menu can unmount without the same gesture delivering a stray click to the row below (portal menus).
              const fn = item.onClick;
              window.setTimeout(() => fn(), 0);
            }}
          >
            {item.icon ? (
              <ListItemIcon sx={{ minWidth: 36, color: item.danger ? 'error.main' : 'inherit' }}>{item.icon}</ListItemIcon>
            ) : null}
            <ListItemText
              primary={item.label}
              secondary={item.disabled && item.disabledReason ? item.disabledReason : undefined}
              primaryTypographyProps={{
                variant: 'body2',
                color: item.danger ? 'error' : 'text.primary',
              }}
              secondaryTypographyProps={{
                variant: 'caption',
                sx: { display: 'block', whiteSpace: 'normal', lineHeight: 1.35, mt: 0.25 },
              }}
            />
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
}
