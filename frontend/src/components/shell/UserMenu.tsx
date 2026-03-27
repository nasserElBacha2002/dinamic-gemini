import { useState, MouseEvent } from 'react';
import { Avatar, IconButton, Menu, MenuItem, ListItemIcon, ListItemText, Divider, Typography, Box } from '@mui/material';
import LogoutIcon from '@mui/icons-material/Logout';
import { useAuth } from '../../features/auth';

/**
 * Session control in the topbar corner — Re diseño 3.3 §4.3 (logout inside user menu, not a prominent standalone button).
 */
export default function UserMenu() {
  const { user, logout } = useAuth();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);

  const handleOpen = (e: MouseEvent<HTMLElement>) => setAnchor(e.currentTarget);
  const handleClose = () => setAnchor(null);

  const label = user?.username ?? 'User';
  const initial = label.trim().charAt(0).toUpperCase() || '?';

  return (
    <>
      <IconButton
        onClick={handleOpen}
        size="small"
        aria-label="Open account menu"
        aria-controls={open ? 'account-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        sx={{ ml: 1 }}
      >
        <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: '0.9rem' }}>{initial}</Avatar>
      </IconButton>
      <Menu
        id="account-menu"
        anchorEl={anchor}
        open={open}
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{ sx: { minWidth: 220 } }}
      >
        <Box sx={{ px: 2, py: 1.5, maxWidth: 280 }}>
          <Typography variant="subtitle2" noWrap>
            {label}
          </Typography>
        </Box>
        <Divider />
        <MenuItem
          onClick={() => {
            handleClose();
            logout();
          }}
        >
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Log out</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}
