import { Link as RouterLink } from 'react-router-dom';
import { Link, Tooltip, Typography } from '@mui/material';

export interface RelatedEntityCellProps {
  /** Display name when the relation exists. */
  name: string | null | undefined;
  /** Empty-state label (e.g. "Sin cliente"). */
  emptyLabel: string;
  /** Optional navigation target when the entity can be opened. */
  to?: string | null;
  /** Optional max width for truncation (default 180). */
  maxWidth?: number;
  /** Optional data-testid for the cell root. */
  testId?: string;
}

/**
 * Compact related-entity cell for list tables: truncated name + tooltip, optional link,
 * or muted empty label when the association is missing.
 */
export default function RelatedEntityCell({
  name,
  emptyLabel,
  to,
  maxWidth = 180,
  testId,
}: RelatedEntityCellProps) {
  const trimmed = typeof name === 'string' ? name.trim() : '';
  if (!trimmed) {
    return (
      <Typography
        component="span"
        variant="body2"
        color="text.secondary"
        data-testid={testId}
        noWrap
        sx={{ maxWidth, display: 'inline-block' }}
      >
        {emptyLabel}
      </Typography>
    );
  }

  const textSx = {
    maxWidth,
    display: 'inline-block',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    verticalAlign: 'bottom',
    fontWeight: 500,
  };

  const content = to ? (
    <Link
      component={RouterLink}
      to={to}
      underline="hover"
      color="text.primary"
      data-testid={testId}
      sx={textSx}
      onClick={(e) => e.stopPropagation()}
    >
      {trimmed}
    </Link>
  ) : (
    <Typography component="span" variant="body2" data-testid={testId} sx={textSx}>
      {trimmed}
    </Typography>
  );

  return (
    <Tooltip title={trimmed} placement="top-start" enterDelay={400}>
      <span style={{ maxWidth, display: 'inline-block', verticalAlign: 'bottom' }}>{content}</span>
    </Tooltip>
  );
}
