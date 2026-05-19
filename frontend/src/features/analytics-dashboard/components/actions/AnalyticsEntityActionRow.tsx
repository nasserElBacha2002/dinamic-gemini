import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export interface AnalyticsEntityAction {
  id: string;
  label: string;
  href?: string;
  onClick?: () => void;
  disabled?: boolean;
  tooltip?: string;
  testId?: string;
  tone?: 'primary' | 'secondary';
}

export interface AnalyticsEntityActionRowProps {
  actions: readonly AnalyticsEntityAction[];
}

function ActionLink({ action }: { action: AnalyticsEntityAction }) {
  const variant = action.tone === 'secondary' ? 'caption' : 'body2';

  if (action.disabled) {
    if (!action.tooltip) return null;
    return (
      <Tooltip title={action.tooltip}>
        <Typography variant="caption" color="text.disabled" component="span" data-testid={action.testId}>
          {action.label}
        </Typography>
      </Tooltip>
    );
  }

  if (action.href) {
    return (
      <MuiLink component={RouterLink} to={action.href} variant={variant} underline="hover" data-testid={action.testId}>
        {action.label}
      </MuiLink>
    );
  }

  if (action.onClick) {
    return (
      <MuiLink
        component="button"
        type="button"
        variant={variant}
        underline="hover"
        onClick={action.onClick}
        data-testid={action.testId}
        sx={{ cursor: 'pointer', border: 0, bgcolor: 'transparent', p: 0 }}
      >
        {action.label}
      </MuiLink>
    );
  }

  return null;
}

export function AnalyticsEntityActionRow({ actions }: AnalyticsEntityActionRowProps) {
  const visible = actions.filter((action) => {
    if (action.disabled && !action.tooltip) return false;
    return Boolean(action.href || action.onClick || (action.disabled && action.tooltip));
  });

  if (!visible.length) return null;

  return (
    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
      {visible.map((action) => (
        <ActionLink key={action.id} action={action} />
      ))}
    </Box>
  );
}
