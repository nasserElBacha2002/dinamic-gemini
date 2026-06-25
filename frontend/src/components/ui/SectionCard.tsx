/**
 * SectionCard — Re diseño 3.3 §8.8: group metrics, tables, summaries, activity, secondary metadata.
 * Keeps page composition: context → metrics → main content (§2.2).
 */

import type { ReactNode } from 'react';
import { Box, Card, CardContent, Typography } from '@mui/material';

export interface SectionCardProps {
  /** Section heading (e.g. "Aisles", "Recent activity"). */
  title?: string;
  subtitle?: string;
  /** Header row actions (Refresh, View all, etc.). */
  actions?: ReactNode;
  children: ReactNode;
  variant?: 'outlined' | 'elevation';
  elevation?: number;
  /** Optional stable selector for tests. */
  testId?: string;
}

export default function SectionCard({
  title,
  subtitle,
  actions,
  children,
  variant = 'outlined',
  elevation = 1,
  testId,
}: SectionCardProps) {
  const hasHeader = Boolean(title) || Boolean(subtitle) || Boolean(actions);

  return (
    <Card
      variant={variant}
      elevation={variant === 'elevation' ? elevation : undefined}
      data-testid={testId}
      sx={{ mb: 0, minWidth: 0, maxWidth: '100%' }}
    >
      {hasHeader ? (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 2,
            px: 2,
            pt: 2,
            pb: title || subtitle ? 1 : 2,
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            {title ? (
              <Typography variant="subtitle1" component="h2" fontWeight={600}>
                {title}
              </Typography>
            ) : null}
            {subtitle ? (
              <Typography
                variant="body2"
                color="text.secondary"
                component="p"
                sx={{ mt: title ? 0.5 : 0 }}
              >
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {actions ? <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>{actions}</Box> : null}
        </Box>
      ) : null}
      <CardContent sx={{ pt: hasHeader ? 0 : 2, '&:last-child': { pb: 2 } }}>{children}</CardContent>
    </Card>
  );
}
