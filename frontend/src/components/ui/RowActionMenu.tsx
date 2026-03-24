/**
 * RowActionMenu — Re diseño 3.3 §8.7, §15.6: row actions without crowding tables with buttons.
 */

import { useState, MouseEvent } from 'react';
import { IconButton, ListItemIcon, ListItemText, Menu, MenuItem } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';

export interface RowActionMenuItem {
  id: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  /** Destructive row action — uses error tone (§6.3). */
  danger?: boolean;
  /** Optional leading icon. */
  icon?: React.ReactNode;
}

export interface RowActionMenuProps {
  items: RowActionMenuItem[];
  /** Accessible label for the trigger (e.g. "Actions for row SKU-123"). */
  ariaLabel: string;
  /** Optional icon button size. */
  size?: 'small' | 'medium' | 'large';
}

export default function RowActionMenu({ items, ariaLabel, size = 'small' }: RowActionMenuProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);

  const handleOpen = (e: MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    setAnchor(e.currentTarget);
  };
  const handleClose = () => setAnchor(null);

  return (
    <>
      <IconButton
        size={size}
        aria-label={ariaLabel}
        aria-controls={open ? 'row-action-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleOpen}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        id="row-action-menu"
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
            onClick={() => {
              handleClose();
              item.onClick();
            }}
          >
            {item.icon ? (
              <ListItemIcon sx={{ minWidth: 36, color: item.danger ? 'error.main' : 'inherit' }}>{item.icon}</ListItemIcon>
            ) : null}
            <ListItemText
              primary={item.label}
              primaryTypographyProps={{
                variant: 'body2',
                color: item.danger ? 'error' : 'text.primary',
              }}
            />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
