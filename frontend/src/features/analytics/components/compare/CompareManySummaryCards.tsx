import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Box, Paper, Tooltip, Typography } from '@mui/material';

type CompareManySummaryCardsProps = {
  summaryTitle: string;
  summaryNotRanking: string;
  summaryValuesText: string;
  executionCaption: string;
};

export default function CompareManySummaryCards({
  summaryTitle,
  summaryNotRanking,
  summaryValuesText,
  executionCaption,
}: CompareManySummaryCardsProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle1">{summaryTitle}</Typography>
        <Tooltip title={summaryNotRanking}>
          <InfoOutlinedIcon fontSize="small" color="action" />
        </Tooltip>
      </Box>
      <Typography variant="body2">{summaryNotRanking}</Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
        {summaryValuesText}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
        {executionCaption}
      </Typography>
    </Paper>
  );
}
