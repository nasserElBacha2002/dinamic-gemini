import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import type { ProcessingUrlFilters } from './utils/processingUrlFilters';

const STATUS_OPTIONS = [
  '',
  'pending',
  'processing',
  'resolved',
  'failed',
  'manual_review',
  'cancelled',
] as const;

const STRATEGY_OPTIONS = ['', 'INTERNAL', 'EXTERNAL', 'CODE_SCAN', 'INTERNAL_OCR'] as const;
const RESOLVED_BY_OPTIONS = ['', 'internal', 'external', 'manual', 'none'] as const;

export interface ProcessingAssetFiltersProps {
  filters: ProcessingUrlFilters;
  onChange: (patch: Partial<ProcessingUrlFilters>) => void;
}

export default function ProcessingAssetFilters({ filters, onChange }: ProcessingAssetFiltersProps) {
  const { t } = useTranslation();

  const statusItems = useMemo(
    () =>
      STATUS_OPTIONS.map((value) => ({
        value,
        label: value ? t(`processing.status.${value}`, { defaultValue: value }) : t('processing.filters.all'),
      })),
    [t]
  );

  return (
    <Stack
      direction={{ xs: 'column', md: 'row' }}
      spacing={1.5}
      sx={{ flexWrap: 'wrap' }}
      data-testid="processing-asset-filters"
    >
      <TextField
        size="small"
        label={t('processing.filters.search')}
        value={filters.search}
        onChange={(e) => onChange({ search: e.target.value, page: 1 })}
        sx={{ minWidth: { md: 200 }, flex: 1 }}
        inputProps={{ 'data-testid': 'processing-filter-search' }}
      />

      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel id="processing-filter-status">{t('processing.filters.status')}</InputLabel>
        <Select
          labelId="processing-filter-status"
          label={t('processing.filters.status')}
          value={filters.status}
          onChange={(e) => onChange({ status: e.target.value, page: 1 })}
          data-testid="processing-filter-status"
        >
          {statusItems.map((item) => (
            <MenuItem key={item.value || '__all'} value={item.value}>
              {item.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel id="processing-filter-strategy">{t('processing.filters.strategy')}</InputLabel>
        <Select
          labelId="processing-filter-strategy"
          label={t('processing.filters.strategy')}
          value={filters.strategy}
          onChange={(e) => onChange({ strategy: e.target.value, page: 1 })}
          data-testid="processing-filter-strategy"
        >
          {STRATEGY_OPTIONS.map((value) => (
            <MenuItem key={value || '__all'} value={value}>
              {value || t('processing.filters.all')}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel id="processing-filter-resolved">{t('processing.filters.resolvedBy')}</InputLabel>
        <Select
          labelId="processing-filter-resolved"
          label={t('processing.filters.resolvedBy')}
          value={filters.resolvedBy}
          onChange={(e) => onChange({ resolvedBy: e.target.value, page: 1 })}
          data-testid="processing-filter-resolved-by"
        >
          {RESOLVED_BY_OPTIONS.map((value) => (
            <MenuItem key={value || '__all'} value={value}>
              {value ? t(`processing.resolvedBy.${value}`, { defaultValue: value }) : t('processing.filters.all')}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={filters.hasWarnings === true}
              onChange={(e) =>
                onChange({ hasWarnings: e.target.checked ? true : null, page: 1 })
              }
              inputProps={{ 'data-testid': 'processing-filter-has-warnings' } as never}
            />
          }
          label={t('processing.filters.hasWarnings')}
        />
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={filters.hasFallback === true}
              onChange={(e) =>
                onChange({ hasFallback: e.target.checked ? true : null, page: 1 })
              }
              inputProps={{ 'data-testid': 'processing-filter-has-fallback' } as never}
            />
          }
          label={t('processing.filters.hasFallback')}
        />
      </Box>
    </Stack>
  );
}
