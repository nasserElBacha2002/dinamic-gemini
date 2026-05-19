import { Box, Typography } from '@mui/material';
import type { AnalyticsMetadataItem } from '../base/AnalyticsMetadataGrid';
import { AnalyticsCard } from '../base/AnalyticsCard';
import { AnalyticsEmptyText } from '../base/AnalyticsEmptyText';
import { AnalyticsMetadataGrid } from '../base/AnalyticsMetadataGrid';
import type { AnalyticsEntityAction } from '../actions/AnalyticsEntityActionRow';
import { AnalyticsEntityActionRow } from '../actions/AnalyticsEntityActionRow';

export interface AnalyticsEntityRankingCardItem {
  id: string;
  title: string;
  subtitle?: React.ReactNode;
  metadata: readonly AnalyticsMetadataItem[];
  actions: readonly AnalyticsEntityAction[];
  testId?: string;
}

export interface AnalyticsEntityRankingCardsProps {
  items: readonly AnalyticsEntityRankingCardItem[];
  emptyText: string;
  testId?: string;
}

export function AnalyticsEntityRankingCards({ items, emptyText, testId }: AnalyticsEntityRankingCardsProps) {
  if (!items.length) {
    return <AnalyticsEmptyText data-testid={testId ? `${testId}-empty` : undefined}>{emptyText}</AnalyticsEmptyText>;
  }

  return (
    <Box data-testid={testId} sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {items.map((item) => (
        <AnalyticsCard key={item.id} data-testid={item.testId ?? (testId ? `${testId}-item-${item.id}` : undefined)}>
          <Typography variant="body2" fontWeight={700} gutterBottom={Boolean(item.subtitle)}>
            {item.title}
          </Typography>
          {item.subtitle ? (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              {item.subtitle}
            </Typography>
          ) : null}
          {item.metadata.length > 0 ? (
            <Box sx={{ mb: 1 }}>
              <AnalyticsMetadataGrid items={item.metadata} />
            </Box>
          ) : null}
          <AnalyticsEntityActionRow actions={item.actions} />
        </AnalyticsCard>
      ))}
    </Box>
  );
}
