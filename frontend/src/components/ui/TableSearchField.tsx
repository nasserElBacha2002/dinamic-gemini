/**
 * Shared MUI search field for table toolbars — consistent size, placeholder, clear affordance.
 */

import type { ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { IconButton, InputAdornment, TextField } from '@mui/material';
import ClearIcon from '@mui/icons-material/Clear';

export type TableSearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  /** Shown when non-empty; clears input. */
  showClear?: boolean;
  disabled?: boolean;
  /** Optional override; defaults to `table.search_label` / `table.search_placeholder`. */
  label?: string;
  placeholder?: string;
  /** Minimum width in px for flex toolbars. */
  minWidth?: number;
  'data-testid'?: string;
};

export default function TableSearchField({
  value,
  onChange,
  showClear = true,
  disabled = false,
  label,
  placeholder,
  minWidth = 200,
  'data-testid': dataTestId,
}: TableSearchFieldProps) {
  const { t } = useTranslation();
  const resolvedLabel = label ?? t('table.search_label');
  const resolvedPlaceholder = placeholder ?? t('table.search_placeholder');

  return (
    <TextField
      size="small"
      label={resolvedLabel}
      placeholder={resolvedPlaceholder}
      value={value}
      disabled={disabled}
      data-testid={dataTestId}
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
      sx={{ minWidth, flex: '1 1 180px', maxWidth: 360 }}
      inputProps={{ 'data-datatable-skip-row-click': '' }}
      InputProps={{
        endAdornment:
          showClear && value ? (
            <InputAdornment position="end">
              <IconButton
                size="small"
                aria-label={t('table.clear_search_aria')}
                onClick={() => onChange('')}
                edge="end"
              >
                <ClearIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ) : undefined,
      }}
    />
  );
}
