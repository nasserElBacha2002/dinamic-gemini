/**
 * KpiCard — Re diseño 3.3 §8.3: summary metric (label, value, optional context, optional navigation §14.6).
 * Desktop-first medium density (§7.2).
 */

import type { ReactNode, KeyboardEvent } from 'react';
import { Card, CardActionArea, CardContent, Typography } from '@mui/material';

export interface KpiCardProps {
  label: string;
  value: ReactNode;
  /** Optional secondary line (variation, hint). */
  description?: string;
  /** When set, card is interactive (filtered view / drill-down). */
  onClick?: () => void;
  /** Accessible name when `onClick` is used; defaults to label + value text hint. */
  ariaLabel?: string;
}

export default function KpiCard({ label, value, description, onClick, ariaLabel }: KpiCardProps) {
  const content = (
    <CardContent sx={{ '&:last-child': { pb: 2 } }}>
      <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      <Typography variant="h6" component="p" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
        {value}
      </Typography>
      {description ? (
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.75, display: 'block' }}>
          {description}
        </Typography>
      ) : null}
    </CardContent>
  );

  if (onClick) {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick();
      }
    };
    return (
      <Card variant="outlined" sx={{ height: '100%' }}>
        <CardActionArea
          onClick={onClick}
          onKeyDown={handleKeyDown}
          aria-label={ariaLabel ?? `${label}: ${typeof value === 'string' || typeof value === 'number' ? value : label}`}
        >
          {content}
        </CardActionArea>
      </Card>
    );
  }

  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      {content}
    </Card>
  );
}
