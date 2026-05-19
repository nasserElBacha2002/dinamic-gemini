import { Alert, Box, Typography } from '@mui/material';

export interface MetricUnavailableStateProps {
  title: string;
  description: string;
}

export function MetricUnavailableState({ title, description }: MetricUnavailableStateProps) {
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2">{description}</Typography>
    </Alert>
  );
}

export function MetricUnavailableCards({
  cards,
}: {
  cards: readonly { label: string; value: string; description?: string }[];
}) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))' },
        gap: 2,
      }}
    >
      {cards.map((card) => (
        <Box
          key={card.label}
          sx={{
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            p: 2,
            bgcolor: 'action.hover',
          }}
        >
          <Typography variant="caption" color="text.secondary" display="block">
            {card.label}
          </Typography>
          <Typography variant="body1" fontWeight={600}>
            {card.value}
          </Typography>
          {card.description ? (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {card.description}
            </Typography>
          ) : null}
        </Box>
      ))}
    </Box>
  );
}
