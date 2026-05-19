import { Box, Chip, Paper, Tooltip, Typography } from '@mui/material';
import type { CompareRunBenchmarkCardModel } from '../compareBenchmarkViewModel';

type CompareBenchmarkRunCardsProps = {
  cards: CompareRunBenchmarkCardModel[];
  compact?: boolean;
};

export default function CompareBenchmarkRunCards({ cards, compact = false }: CompareBenchmarkRunCardsProps) {
  return (
    <Box
      data-testid="compare-benchmark-run-cards"
      sx={{
        display: 'grid',
        gap: compact ? 1.5 : 2,
        gridTemplateColumns: { xs: '1fr', md: `repeat(${Math.min(cards.length, 3)}, minmax(0, 1fr))` },
      }}
    >
      {cards.map((card) => (
        <Paper
          key={card.jobId}
          variant="outlined"
          sx={{ p: compact ? 1.5 : 2, borderColor: card.isBaseline ? 'primary.main' : 'divider' }}
          data-testid={card.isBaseline ? 'compare-many-baseline-card' : `compare-benchmark-run-card-${card.jobId}`}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1, mb: 1 }}>
            <Typography variant="subtitle1" sx={{ wordBreak: 'break-word' }}>
              {card.providerModelLabel}
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.75, flexShrink: 0 }}>
              {card.isBaseline ? <Chip size="small" color="primary" label={card.baselineChipLabel} /> : null}
              <Chip size="small" label={card.statusLabel} />
            </Box>
          </Box>

          <MetricLine label={card.runCostLabel} value={card.runCostValue} details={card.runCostDetails} />
          <MetricLine label={card.costPerUnitLabel} value={card.costPerUnitValue} />
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25, mb: 0.75 }}>
            {card.costPerUnitHelper}
          </Typography>
          <MetricLine label={card.executionTimeLabel} value={card.executionTimeValue} />
          <MetricLine label={card.quantityLabel} value={card.quantityValue} />
          <MetricLine label={card.reviewRequiredLabel} value={card.reviewRequiredValue} />
          <MetricLine label={card.unknownCodesLabel} value={card.unknownCodesValue} />
          <MetricLine label={card.consolidatedLabel} value={card.consolidatedValue} />
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            {card.costCaptureStatusLabel}: {card.costCaptureStatusValue}
          </Typography>
        </Paper>
      ))}
    </Box>
  );
}

function MetricLine({
  label,
  value,
  details,
}: {
  label: string;
  value: string;
  details?: string | null;
}) {
  const content = (
    <Typography variant="body2" sx={{ mt: 0.35 }}>
      <Typography component="span" variant="body2" color="text.secondary">
        {label}:{' '}
      </Typography>
      {value}
    </Typography>
  );
  if (details) {
    return <Tooltip title={details}>{content}</Tooltip>;
  }
  return content;
}
