import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export interface AnalyticsEntityActionRowProps {
  viewDetailLabel?: string;
  viewDetailHref?: string;
  onViewDetailClick?: () => void;
  viewDetailTestId?: string;
  analyticsLabel: string;
  onAnalyticsClick: () => void;
  analyticsTestId?: string;
  compareLabel: string;
  compareHref?: string;
  compareDisabled?: boolean;
  compareTooltip?: string;
  compareTestId?: string;
}

export function AnalyticsEntityActionRow({
  viewDetailLabel,
  viewDetailHref,
  onViewDetailClick,
  viewDetailTestId,
  analyticsLabel,
  onAnalyticsClick,
  analyticsTestId,
  compareLabel,
  compareHref,
  compareDisabled = false,
  compareTooltip,
  compareTestId,
}: AnalyticsEntityActionRowProps) {
  return (
    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
      {viewDetailLabel && (viewDetailHref || onViewDetailClick) ? (
        onViewDetailClick ? (
          <MuiLink
            component="button"
            type="button"
            variant="body2"
            underline="hover"
            onClick={onViewDetailClick}
            data-testid={viewDetailTestId}
            sx={{ cursor: 'pointer', border: 0, bgcolor: 'transparent', p: 0 }}
          >
            {viewDetailLabel}
          </MuiLink>
        ) : (
          <MuiLink
            component={RouterLink}
            to={viewDetailHref!}
            variant="body2"
            underline="hover"
            data-testid={viewDetailTestId}
          >
            {viewDetailLabel}
          </MuiLink>
        )
      ) : null}
      <MuiLink
        component="button"
        type="button"
        variant="body2"
        underline="hover"
        onClick={onAnalyticsClick}
        data-testid={analyticsTestId}
        sx={{ cursor: 'pointer', border: 0, bgcolor: 'transparent', p: 0 }}
      >
        {analyticsLabel}
      </MuiLink>
      {compareHref && !compareDisabled ? (
        <MuiLink component={RouterLink} to={compareHref} variant="body2" underline="hover" data-testid={compareTestId}>
          {compareLabel}
        </MuiLink>
      ) : compareTooltip ? (
        <Tooltip title={compareTooltip}>
          <Typography
            variant="caption"
            color="text.disabled"
            component="span"
            data-testid={compareTestId}
          >
            {compareLabel}
          </Typography>
        </Tooltip>
      ) : null}
    </Box>
  );
}
