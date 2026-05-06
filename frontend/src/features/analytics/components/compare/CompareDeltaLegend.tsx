import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Box, Paper, Tooltip, Typography } from '@mui/material';

type CompareDeltaLegendProps = {
  title: string;
  body: string;
};

export default function CompareDeltaLegend({ title, body }: CompareDeltaLegendProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle2">{title}</Typography>
        <Tooltip title={body}>
          <InfoOutlinedIcon fontSize="small" color="action" />
        </Tooltip>
      </Box>
      <Typography variant="caption" color="text.secondary">
        {body}
      </Typography>
    </Paper>
  );
}
