import { Box, FormControl, InputLabel, MenuItem, Paper, Select, Typography } from '@mui/material';

type AisleOption = {
  id: string;
  code: string;
};

type CompareScopeSelectorProps = {
  isAisleSelected: boolean;
  aisles: AisleOption[];
  aisleSelectValue: string;
  onAisleChange: (nextAisleId: string) => void;
  selectAisleTitle: string;
  aisleLabel: string;
  placeholderLabel: string;
  changeAisleLabel: string;
};

export default function CompareScopeSelector({
  isAisleSelected,
  aisles,
  aisleSelectValue,
  onAisleChange,
  selectAisleTitle,
  aisleLabel,
  placeholderLabel,
  changeAisleLabel,
}: CompareScopeSelectorProps) {
  if (!isAisleSelected) {
    return (
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-runs-aisle-scope">
        <Typography variant="subtitle2" gutterBottom>
          {selectAisleTitle}
        </Typography>
        <FormControl fullWidth size="small" sx={{ maxWidth: 360 }}>
          <InputLabel id="analytics-aisle-label">{aisleLabel}</InputLabel>
          <Select
            labelId="analytics-aisle-label"
            label={aisleLabel}
            value=""
            displayEmpty
            onChange={(e) => onAisleChange(String(e.target.value))}
          >
            <MenuItem value="" disabled>
              <em>{placeholderLabel}</em>
            </MenuItem>
            {aisles.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.code}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Paper>
    );
  }

  return (
    <Box
      data-testid="compare-runs-change-aisle"
      sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}
    >
      <FormControl size="small" sx={{ minWidth: 200 }}>
        <InputLabel id="switch-aisle-label">{changeAisleLabel}</InputLabel>
        <Select
          labelId="switch-aisle-label"
          label={changeAisleLabel}
          value={aisleSelectValue}
          onChange={(e) => onAisleChange(String(e.target.value))}
        >
          {aisles.map((a) => (
            <MenuItem key={a.id} value={a.id}>
              {a.code}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  );
}
