import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Collapse,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { FilterToolbar } from '../../../components/ui';
import type { AnalyticsDashboardFilters } from '../types';

export interface AnalyticsFilterBarProps {
  filters: AnalyticsDashboardFilters;
  onChange: (next: AnalyticsDashboardFilters) => void;
  onApply: () => void;
  onReset: () => void;
  inventories: readonly { id: string; name: string }[];
  aisles: readonly { id: string; code: string }[];
  inventoriesLoadFailed: boolean;
  isRefreshing: boolean;
  /** True when URL filters match applied — disables Actualizar until something changes. */
  applyDisabled?: boolean;
}

export function AnalyticsFilterBar({
  filters,
  onChange,
  onApply,
  onReset,
  inventories,
  aisles,
  inventoriesLoadFailed,
  isRefreshing,
  applyDisabled = false,
}: AnalyticsFilterBarProps) {
  const { t } = useTranslation();
  const [moreOpen, setMoreOpen] = useState(false);

  const patch = (partial: Partial<AnalyticsDashboardFilters>) => onChange({ ...filters, ...partial });

  return (
    <Box sx={{ mb: 2 }}>
      <FilterToolbar
        onReset={onReset}
        endActions={
          <Button
            size="small"
            variant="contained"
            onClick={onApply}
            disabled={isRefreshing || applyDisabled}
            data-testid="analytics-apply-filters"
          >
            {t('analyticsDashboard.actions.refresh')}
          </Button>
        }
      >
        <TextField
          size="small"
          label={t('common.from')}
          type="date"
          value={filters.dateFrom}
          onChange={(e) => patch({ dateFrom: e.target.value })}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <TextField
          size="small"
          label={t('common.to')}
          type="date"
          value={filters.dateTo}
          onChange={(e) => patch({ dateTo: e.target.value })}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="analytics-inv-label">{t('common.inventory')}</InputLabel>
          <Select
            labelId="analytics-inv-label"
            label={t('common.inventory')}
            value={filters.inventoryId}
            onChange={(e) => patch({ inventoryId: e.target.value, aisleId: '' })}
          >
            <MenuItem value="">{t('analytics.scope_inventory_all')}</MenuItem>
            {inventories.map((inv) => (
              <MenuItem key={inv.id} value={inv.id}>
                {inv.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }} disabled={!filters.inventoryId}>
          <InputLabel id="analytics-aisle-label">{t('common.aisle')}</InputLabel>
          <Select
            labelId="analytics-aisle-label"
            label={t('common.aisle')}
            value={filters.aisleId && aisles.some((a) => a.id === filters.aisleId) ? filters.aisleId : ''}
            onChange={(e) => patch({ aisleId: e.target.value })}
          >
            <MenuItem value="">{t('analytics.all_aisles_option')}</MenuItem>
            {aisles.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.code}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button size="small" variant="text" onClick={() => setMoreOpen((v) => !v)}>
          {t('analyticsDashboard.filters.more')}
        </Button>
      </FilterToolbar>

      <Collapse in={moreOpen}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mt: 1, mb: 1 }}>
          <TextField
            size="small"
            label={t('analyticsDashboard.filters.client')}
            value={filters.clientId}
            onChange={(e) => patch({ clientId: e.target.value })}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label={t('analyticsDashboard.filters.supplier')}
            value={filters.clientSupplierId}
            onChange={(e) => patch({ clientSupplierId: e.target.value })}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label={t('observability.metrics.provider')}
            value={filters.providerName}
            onChange={(e) => patch({ providerName: e.target.value })}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label={t('observability.metrics.model')}
            value={filters.modelName}
            onChange={(e) => patch({ modelName: e.target.value })}
            sx={{ minWidth: 160 }}
          />
        </Box>
      </Collapse>

      <Typography variant="caption" color="text.secondary" display="block" data-testid="analytics-filter-scope-note">
        {t('analyticsDashboard.filters.partialScopeNote')}
      </Typography>

      {inventoriesLoadFailed ? (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {t('analytics.filter_options_load_failed')}
        </Alert>
      ) : null}
    </Box>
  );
}
